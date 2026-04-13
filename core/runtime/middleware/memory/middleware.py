"""MemoryMiddleware — Context pruning + compaction.

Combines SessionPruner (Layer 1) and ContextCompactor (Layer 2).
All operations happen in awrap_model_call — modifies the request sent to LLM,
does NOT modify LangGraph state. TUI sees full history, agent sees compressed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain_core.messages import SystemMessage

from core.runtime.checkpoint_store import CheckpointStore
from core.runtime.langgraph_checkpoint_store import LangGraphCheckpointStore
from core.runtime.middleware import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from storage.contracts import SummaryRepo

from .compactor import ContextCompactor
from .pruner import SessionPruner
from .summary_store import SummaryStore

logger = logging.getLogger(__name__)
_COMPACTION_BREAKER_THRESHOLD = 3


class MemoryMiddleware(AgentMiddleware):
    """Context memory management middleware.

    Layer 1 (Pruning): trim/clear old ToolMessage content
    Layer 2 (Compaction): LLM summarization when context exceeds threshold
    """

    tools = ()  # no tools injected

    def __init__(
        self,
        context_limit: int = 100000,
        pruning_config: Any = None,
        compaction_config: Any = None,
        db_path: Path | None = None,
        summary_repo: SummaryRepo | None = None,
        checkpointer: Any = None,
        compaction_threshold: float = 0.7,
        verbose: bool = False,
    ):
        self.verbose = verbose
        self._context_limit = context_limit
        self._compaction_threshold = compaction_threshold
        trigger_tokens = getattr(compaction_config, "trigger_tokens", None)
        self._compaction_trigger_tokens = int(trigger_tokens) if trigger_tokens else None

        # Layer 1: Pruner
        if pruning_config:
            self.pruner = SessionPruner(
                soft_trim_chars=pruning_config.soft_trim_chars,
                hard_clear_threshold=pruning_config.hard_clear_threshold,
                protect_recent=pruning_config.protect_recent,
            )
        else:
            self.pruner = SessionPruner()

        # Layer 2: Compactor
        if compaction_config:
            self.compactor = ContextCompactor(
                reserve_tokens=compaction_config.reserve_tokens,
                keep_recent_tokens=compaction_config.keep_recent_tokens,
            )
        else:
            self.compactor = ContextCompactor()

        # Persistent storage
        summary_db_path = db_path or Path.home() / ".leon" / "leon.db"
        self.summary_store = SummaryStore(summary_db_path, summary_repo=summary_repo) if (db_path or summary_repo) else None
        self._checkpointer: Any = None
        self._checkpoint_store: CheckpointStore | None = None
        self.checkpointer = checkpointer

        # Injected references (set by agent.py after construction)
        self._model: Any = None
        self._model_config: dict[str, Any] | None = None
        self._runtime: Any = None

        # Compaction cache
        self._cached_summary: str | None = None
        self._compact_up_to_index: int = 0
        self._summary_restored: bool = False
        self._summary_thread_id: str | None = None
        self._pending_owner_notices: list[dict[str, Any]] = []
        self._compaction_failure_counts_by_thread: dict[str, int] = {}
        self._compaction_breaker_open_by_thread: dict[str, bool] = {}

        if verbose:
            print("[MemoryMiddleware] Initialized")
            if self.summary_store:
                print(f"[MemoryMiddleware] SummaryStore enabled at {db_path}")

    def set_model(self, model: Any, model_config: dict[str, Any] | None = None) -> None:
        """Inject LLM model reference (called by agent.py).

        model_config: configurable fields (model, api_key, base_url, etc.)
        so compact invokes the correct model, not the ConfigurableModel default.
        """
        self._model = model
        self._model_config = model_config

    @property
    def checkpointer(self) -> Any:
        return self._checkpointer

    @checkpointer.setter
    def checkpointer(self, value: Any) -> None:
        self._checkpointer = value
        self._checkpoint_store = LangGraphCheckpointStore(value) if value is not None else None

    @property
    def _resolved_model(self) -> Any:
        """Return model with config bound so it uses the correct model/provider."""
        if self._model_config and hasattr(self._model, "with_config"):
            return self._model.with_config(configurable=self._model_config)
        return self._model

    def set_context_limit(self, context_limit: int) -> None:
        """Update context limit (called on model switch).

        Also caps keep_recent_tokens so compactor can actually split
        messages when context_limit is small.
        """
        self._context_limit = context_limit
        # @@@keep-recent-cap — keep_recent must be < threshold, otherwise
        # split_messages keeps everything and compact never actually runs.
        max_keep = int(context_limit * 0.4)
        if self.compactor.keep_recent_tokens > max_keep > 0:
            self.compactor.keep_recent_tokens = max_keep

    def set_runtime(self, runtime: Any) -> None:
        """Inject AgentRuntime reference (called by agent.py)."""
        self._runtime = runtime

    @property
    def compact_boundary_index(self) -> int:
        return self._compact_up_to_index

    def _compaction_threshold_tokens(self) -> int:
        return self._compaction_trigger_tokens or int(self._context_limit * self._compaction_threshold)

    def _should_compact(self, estimated_tokens: int) -> bool:
        return estimated_tokens > self._compaction_threshold_tokens()

    # ========== AgentMiddleware interface ==========

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        messages = list(request.messages)
        original_count = len(messages)
        thread_id = self._extract_thread_id(request)

        # Restore summary from store if not already done
        if not self._summary_restored and self.summary_store:
            if thread_id:
                await self._restore_summary_from_store(thread_id)
                self._summary_restored = True
                self._summary_thread_id = thread_id
        elif self.summary_store and thread_id and self._summary_thread_id != thread_id:
            await self._restore_summary_from_store(thread_id)
            self._summary_restored = True
            self._summary_thread_id = thread_id

        sys_tokens = self._estimate_system_tokens(request)

        # Layer 1: Prune old ToolMessage content
        pre_prune_tokens = self._estimate_tokens(messages) + sys_tokens
        messages = self.pruner.prune(messages)
        post_prune_tokens = self._estimate_tokens(messages) + sys_tokens

        if self.verbose:
            pruned_saved = pre_prune_tokens - post_prune_tokens
            if pruned_saved > 0:
                print(f"[Memory] Pruned: {pre_prune_tokens} → {post_prune_tokens} tokens (saved ~{pruned_saved})")
            for i, (orig, pruned) in enumerate(zip(request.messages, messages)):
                if orig is not pruned and orig.__class__.__name__ == "ToolMessage":
                    orig_len = len(getattr(orig, "content", ""))
                    new_len = len(getattr(pruned, "content", ""))
                    action = "hard-clear" if "[Tool output cleared" in pruned.content else "soft-trim"
                    print(f"[Memory]   msg[{i}] ToolMessage: {orig_len} → {new_len} chars ({action})")

        # Layer 2: Compaction
        summarized_messages = self._messages_with_cached_summary(messages)
        estimate_source = summarized_messages if summarized_messages is not None else messages
        estimated = self._estimate_tokens(estimate_source) + sys_tokens
        if self.verbose:
            threshold = self._compaction_threshold_tokens()
            should_compact = self._should_compact(estimated)
            print(
                f"[Memory] Context: ~{estimated} tokens "
                f"(sys={sys_tokens}, msgs={estimated - sys_tokens}), "
                f"limit={self._context_limit}, threshold={threshold}, "
                f"compact={'YES' if should_compact else 'no'}"
            )

        if self._should_compact(estimated) and self._model:
            compacted = await self._attempt_compaction(messages, thread_id=thread_id)
            if compacted is not None:
                messages = compacted
        elif summarized_messages is not None:
            messages = summarized_messages

        if self.verbose:
            final_tokens = self._estimate_tokens(messages) + sys_tokens
            print(f"[Memory] Final: {len(messages)} msgs (~{final_tokens} tokens) sent to LLM (original: {original_count} msgs)")

        response = await handler(request.override(messages=messages))
        if response.request_messages is None:
            return ModelResponse(
                result=response.result,
                request_messages=list(messages),
                prepared_request=response.prepared_request,
            )
        return response

    async def _do_compact(self, messages: list[Any], thread_id: str | None = None) -> list[Any]:
        """Execute compaction: summarize old messages, return compacted list."""
        if self._runtime:
            self._runtime.set_flag("is_compacting", True)
        try:
            to_summarize, to_keep = self.compactor.split_messages(messages)
            if len(to_summarize) < 2:
                return messages

            self._emit_compaction_start_notice()
            is_split_turn, turn_prefix = self.compactor.detect_split_turn(messages, to_keep, self._context_limit)

            if is_split_turn:
                summary_text, prefix_summary = await self.compactor.compact_with_split_turn(to_summarize, turn_prefix, self._resolved_model)
                to_keep = to_keep[len(turn_prefix) :]
                if self.verbose:
                    print(
                        f"[Memory] Split turn detected: {len(to_summarize)} history msgs + "
                        f"{len(turn_prefix)} prefix msgs → summary + {len(to_keep)} suffix msgs"
                    )
            else:
                summary_text = await self.compactor.compact(to_summarize, self._resolved_model)
                prefix_summary = None
                if self.verbose:
                    print(f"[Memory] Compacted: {len(to_summarize)} msgs → summary + {len(to_keep)} recent")

            self._cached_summary = summary_text
            self._compact_up_to_index = len(messages) - len(to_keep)
            self._summary_restored = True
            self._summary_thread_id = thread_id
            self._record_compaction_notice()

            if self.summary_store and thread_id:
                try:
                    summary_id = self.summary_store.save_summary(
                        thread_id=thread_id,
                        summary_text=summary_text,
                        compact_up_to_index=self._compact_up_to_index,
                        compacted_at=len(messages),
                        is_split_turn=is_split_turn,
                        split_turn_prefix=prefix_summary,
                    )
                    if self.verbose:
                        print(f"[Memory] Saved summary {summary_id} to store")
                except Exception as e:
                    logger.error(f"[Memory] Failed to save summary to store: {e}")

            summary_msg = SystemMessage(content=f"[Conversation Summary]\n{summary_text}")
            return [summary_msg] + to_keep
        finally:
            if self._runtime:
                self._runtime.set_flag("is_compacting", False)

    async def force_compact(self, messages: list[Any]) -> dict[str, Any] | None:
        """Manual compaction trigger (/compact command). Ignores threshold."""
        if not self._model:
            return None

        pruned = self.pruner.prune(messages)
        to_summarize, to_keep = self.compactor.split_messages(pruned)
        if len(to_summarize) < 2:
            return None

        if self._runtime:
            self._runtime.set_flag("is_compacting", True)
        try:
            self._emit_compaction_start_notice()
            summary_text = await self.compactor.compact(to_summarize, self._resolved_model)
            self._cached_summary = summary_text
            self._compact_up_to_index = len(messages) - len(to_keep)
            self._record_compaction_notice()
            return {
                "stats": {
                    "summarized": len(to_summarize),
                    "kept": len(to_keep),
                }
            }
        finally:
            if self._runtime:
                self._runtime.set_flag("is_compacting", False)

    async def compact_messages_for_recovery(self, messages: list[Any], thread_id: str | None = None) -> list[Any] | None:
        """Force a compaction pass and return the compacted message list."""
        if not self._model:
            return None

        pruned = self.pruner.prune(messages)
        to_summarize, to_keep = self.compactor.split_messages(pruned)
        if len(to_summarize) < 2:
            return None

        return await self._attempt_compaction(
            pruned,
            thread_id=thread_id or self._current_thread_id(),
            respect_breaker=False,
            record_failures=False,
            clear_breaker_on_success=True,
        )

    def _estimate_tokens(self, messages: list[Any]) -> int:
        """Estimate total tokens for messages (chars // 2)."""
        total = 0
        for msg in messages:
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total += len(block.get("text", ""))
                    elif isinstance(block, str):
                        total += len(block)
        return total // 2

    def _estimate_system_tokens(self, request: Any) -> int:
        """Estimate tokens for system_message (not in messages list)."""
        sys_msg = getattr(request, "system_message", None)
        if not sys_msg:
            return 0
        content = getattr(sys_msg, "content", "")
        return len(content) // 2 if isinstance(content, str) else 0

    def _extract_thread_id(self, request: ModelRequest) -> str | None:
        """Extract thread_id from thread context (ContextVar set by streaming/agent)."""
        from sandbox.thread_context import get_current_thread_id

        tid = get_current_thread_id()
        if tid:
            return tid
        # Fallback: try request.config (used in tests)
        config = getattr(request, "config", None)
        if not config:
            return None
        configurable = getattr(config, "configurable", None)
        if isinstance(configurable, dict):
            return configurable.get("thread_id")
        return getattr(configurable, "thread_id", None) if configurable else None

    def consume_pending_notices(self) -> list[dict[str, Any]]:
        notices = list(self._pending_owner_notices)
        self._pending_owner_notices.clear()
        return notices

    def _messages_with_cached_summary(self, messages: list[Any]) -> list[Any] | None:
        if not self._cached_summary or self._compact_up_to_index <= 0 or self._compact_up_to_index > len(messages):
            return None
        summary_msg = SystemMessage(content=f"[Conversation Summary]\n{self._cached_summary}")
        summarized = [summary_msg] + messages[self._compact_up_to_index :]
        if self.verbose:
            print(f"[Memory] Using cached summary: {self._compact_up_to_index} old msgs replaced, {len(summarized) - 1} msgs sent to LLM")
        return summarized

    def snapshot_thread_state(self, thread_id: str) -> dict[str, Any]:
        return {
            "failure_count": int(self._compaction_failure_counts_by_thread.get(thread_id, 0)),
            "breaker_open": bool(self._compaction_breaker_open_by_thread.get(thread_id, False)),
        }

    def restore_thread_state(self, thread_id: str, state: dict[str, Any] | None) -> None:
        payload = dict(state or {})
        failure_count = int(payload.get("failure_count") or 0)
        breaker_open = bool(payload.get("breaker_open", False))
        if failure_count > 0:
            self._compaction_failure_counts_by_thread[thread_id] = failure_count
        else:
            self._compaction_failure_counts_by_thread.pop(thread_id, None)
        if breaker_open:
            self._compaction_breaker_open_by_thread[thread_id] = True
        else:
            self._compaction_breaker_open_by_thread.pop(thread_id, None)

    def clear_thread_state(self, thread_id: str) -> None:
        self._compaction_failure_counts_by_thread.pop(thread_id, None)
        self._compaction_breaker_open_by_thread.pop(thread_id, None)

    def _record_compaction_notice(self) -> None:
        content = f"Conversation compacted. Earlier {self._compact_up_to_index} message(s) are now represented by a summary."
        self._queue_owner_notice(
            {
                "content": content,
                "notification_type": "compact",
                "compact_boundary_index": self._compact_up_to_index,
            }
        )

    def _emit_compaction_start_notice(self) -> None:
        if not self._runtime or not hasattr(self._runtime, "emit_activity_event"):
            return
        notice = {
            "content": "Compacting conversation. A summary is being prepared.",
            "notification_type": "compact_start",
            "compact_boundary_index": self._compact_up_to_index,
        }
        self._runtime.emit_activity_event(
            {
                "event": "notice",
                "data": json.dumps(notice, ensure_ascii=False),
            }
        )

    def _current_thread_id(self) -> str | None:
        from sandbox.thread_context import get_current_thread_id

        return get_current_thread_id()

    async def _attempt_compaction(
        self,
        messages: list[Any],
        *,
        thread_id: str | None,
        respect_breaker: bool = True,
        record_failures: bool = True,
        clear_breaker_on_success: bool = False,
    ) -> list[Any] | None:
        # @@@compaction-breaker-scope - match cc-src's narrower boundary:
        # the breaker blocks later automatic compaction attempts, but reactive
        # recovery may still try once and clear the breaker on success.
        if respect_breaker and thread_id and self._compaction_breaker_open_by_thread.get(thread_id, False):
            return None
        try:
            compacted = await self._do_compact(messages, thread_id)
        except Exception as exc:
            logger.error("[Memory] Compaction failed for thread %s: %s", thread_id or "<unknown>", exc)
            if record_failures:
                self._record_compaction_failure(thread_id, exc)
            return None
        self._record_compaction_success(thread_id, clear_breaker=clear_breaker_on_success)
        return compacted

    def _record_compaction_success(self, thread_id: str | None, *, clear_breaker: bool = False) -> None:
        if not thread_id:
            return
        self._compaction_failure_counts_by_thread.pop(thread_id, None)
        if clear_breaker:
            self._compaction_breaker_open_by_thread.pop(thread_id, None)

    def _record_compaction_failure(self, thread_id: str | None, exc: Exception) -> None:
        if not thread_id:
            return
        failures = int(self._compaction_failure_counts_by_thread.get(thread_id, 0)) + 1
        self._compaction_failure_counts_by_thread[thread_id] = failures
        if failures < _COMPACTION_BREAKER_THRESHOLD or self._compaction_breaker_open_by_thread.get(thread_id, False):
            return
        self._compaction_breaker_open_by_thread[thread_id] = True
        self._queue_owner_notice(
            {
                "content": "Automatic compaction disabled for this thread after repeated failures. Clear the thread or start a new one.",
                "notification_type": "compact_breaker",
                "failure_count": failures,
                "error": str(exc),
            }
        )

    def _queue_owner_notice(self, notice: dict[str, Any]) -> None:
        self._pending_owner_notices.append(dict(notice))
        if self._runtime and hasattr(self._runtime, "emit_activity_event"):
            # @@@memory-owner-notices - compaction boundary and breaker state are
            # owner-facing runtime facts, so stream and cold rebuild must share
            # the same notice payload instead of inventing separate surfaces.
            self._runtime.emit_activity_event(
                {
                    "event": "notice",
                    "data": json.dumps(notice, ensure_ascii=False),
                }
            )

    async def _restore_summary_from_store(self, thread_id: str) -> None:
        """Restore summary from SummaryStore."""
        if not thread_id:
            raise ValueError(
                "[Memory] thread_id is required for summary persistence. Ensure request.config.configurable contains 'thread_id'."
            )

        try:
            if self.summary_store is None:
                return
            self._cached_summary = None
            self._compact_up_to_index = 0
            summary_data = self.summary_store.get_latest_summary(thread_id)

            if not summary_data:
                if self.verbose:
                    print(f"[Memory] No summary found in store for thread {thread_id}")
                # @@@no-rebuild-on-missing — don't rebuild from checkpointer here.
                # _rebuild_summary_from_checkpointer calls checkpointer.get() which
                # blocks the event loop when checkpointer is AsyncSqliteSaver (the
                # sync .get() uses concurrent.futures internally, deadlocking uvicorn).
                # Normal flow: first compact will create the summary.
                return

            if not summary_data.summary_text or summary_data.compact_up_to_index < 0:
                logger.warning(f"[Memory] Invalid summary data for thread {thread_id}, skipping")
                return

            self._cached_summary = summary_data.summary_text
            self._compact_up_to_index = summary_data.compact_up_to_index
            self._summary_thread_id = thread_id

            if self.verbose:
                print(
                    f"[Memory] Restored summary from store: "
                    f"compact_up_to_index={summary_data.compact_up_to_index}, "
                    f"compacted_at={summary_data.compacted_at}, "
                    f"is_split_turn={summary_data.is_split_turn}"
                )

        except Exception as e:
            self._cached_summary = None
            self._compact_up_to_index = 0
            logger.error(f"[Memory] Failed to restore summary: {e}")

    async def _rebuild_summary_from_checkpointer(self, thread_id: str) -> None:
        """Rebuild summary from checkpointer when store data is corrupted."""
        try:
            if self.summary_store is None or self._checkpoint_store is None:
                return
            if self.verbose:
                print(f"[Memory] Rebuilding summary from checkpointer for thread {thread_id}...")

            checkpoint_state = await self._checkpoint_store.load(thread_id)
            if checkpoint_state is None:
                if self.verbose:
                    print("[Memory] No checkpoint found, skipping rebuild")
                return

            messages = list(checkpoint_state.messages)
            if not messages:
                if self.verbose:
                    print("[Memory] No messages in checkpoint, skipping rebuild")
                return

            estimated = self._estimate_tokens(messages)
            if not self._should_compact(estimated):
                if self.verbose:
                    print("[Memory] Context below threshold, no rebuild needed")
                return

            pruned = self.pruner.prune(messages)
            to_summarize, to_keep = self.compactor.split_messages(pruned)
            if len(to_summarize) < 2:
                if self.verbose:
                    print("[Memory] Not enough messages to summarize, skipping rebuild")
                return

            is_split_turn, turn_prefix = self.compactor.detect_split_turn(pruned, to_keep, self._context_limit)

            if is_split_turn:
                summary_text, prefix_summary = await self.compactor.compact_with_split_turn(to_summarize, turn_prefix, self._resolved_model)
                to_keep = to_keep[len(turn_prefix) :]
            else:
                summary_text = await self.compactor.compact(to_summarize, self._resolved_model)
                prefix_summary = None

            self._cached_summary = summary_text
            self._compact_up_to_index = len(messages) - len(to_keep)

            summary_id = self.summary_store.save_summary(
                thread_id=thread_id,
                summary_text=summary_text,
                compact_up_to_index=self._compact_up_to_index,
                compacted_at=len(messages),
                is_split_turn=is_split_turn,
                split_turn_prefix=prefix_summary,
            )

            if self.verbose:
                print(f"[Memory] Rebuilt and saved summary {summary_id}")

        except Exception as e:
            logger.error(f"[Memory] Failed to rebuild summary from checkpointer: {e}")
