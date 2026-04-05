"""MemoryMiddleware — Context pruning + compaction.

Combines SessionPruner (Layer 1) and ContextCompactor (Layer 2).
All operations happen in awrap_model_call — modifies the request sent to LLM,
does NOT modify LangGraph state. TUI sees full history, agent sees compressed.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import SystemMessage

from storage.contracts import SummaryRepo

from .compactor import ContextCompactor
from .pruner import SessionPruner
from .summary_store import SummaryStore

logger = logging.getLogger(__name__)


class MemoryMiddleware(AgentMiddleware):
    """Context memory management middleware.

    Layer 1 (Pruning): trim/clear old ToolMessage content
    Layer 2 (Compaction): LLM summarization when context exceeds threshold
    """

    tools = []  # no tools injected

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
        self.summary_store = (
            SummaryStore(summary_db_path, summary_repo=summary_repo) if (db_path or summary_repo) else None
        )
        self.checkpointer = checkpointer

        # Injected references (set by agent.py after construction)
        self._model: Any = None
        self._model_config: dict[str, Any] | None = None
        self._runtime: Any = None

        # Compaction cache
        self._cached_summary: str | None = None
        self._compact_up_to_index: int = 0
        self._summary_restored: bool = False

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

    # ========== AgentMiddleware interface ==========

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        messages = list(request.messages)
        original_count = len(messages)

        # Restore summary from store if not already done
        if not self._summary_restored and self.summary_store:
            thread_id = self._extract_thread_id(request)
            if thread_id:
                await self._restore_summary_from_store(thread_id)
                self._summary_restored = True

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
        estimated = self._estimate_tokens(messages) + sys_tokens
        if self.verbose:
            threshold = int(self._context_limit * self._compaction_threshold)
            should_compact = self.compactor.should_compact(estimated, self._context_limit, self._compaction_threshold)
            print(
                f"[Memory] Context: ~{estimated} tokens "
                f"(sys={sys_tokens}, msgs={estimated - sys_tokens}), "
                f"limit={self._context_limit}, threshold={threshold}, "
                f"compact={'YES' if should_compact else 'no'}"
            )

        if self.compactor.should_compact(estimated, self._context_limit, self._compaction_threshold) and self._model:
            thread_id = self._extract_thread_id(request)
            messages = await self._do_compact(messages, thread_id)
        elif self._cached_summary and self._compact_up_to_index > 0:
            if self._compact_up_to_index <= len(messages):
                summary_msg = SystemMessage(content=f"[Conversation Summary]\n{self._cached_summary}")
                messages = [summary_msg] + messages[self._compact_up_to_index :]
                if self.verbose:
                    print(
                        f"[Memory] Using cached summary: "
                        f"{self._compact_up_to_index} old msgs replaced, "
                        f"{len(messages) - 1} msgs sent to LLM"
                    )

        if self.verbose:
            final_tokens = self._estimate_tokens(messages) + sys_tokens
            print(
                f"[Memory] Final: {len(messages)} msgs (~{final_tokens} tokens) "
                f"sent to LLM (original: {original_count} msgs)"
            )

        return await handler(request.override(messages=messages))

    async def _do_compact(self, messages: list[Any], thread_id: str | None = None) -> list[Any]:
        """Execute compaction: summarize old messages, return compacted list."""
        if self._runtime:
            self._runtime.set_flag("isCompacting", True)
        try:
            to_summarize, to_keep = self.compactor.split_messages(messages)
            if len(to_summarize) < 2:
                return messages

            is_split_turn, turn_prefix = self.compactor.detect_split_turn(messages, to_keep, self._context_limit)

            if is_split_turn:
                summary_text, prefix_summary = await self.compactor.compact_with_split_turn(
                    to_summarize, turn_prefix, self._resolved_model
                )
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
                self._runtime.set_flag("isCompacting", False)

    async def force_compact(self, messages: list[Any]) -> dict[str, Any] | None:
        """Manual compaction trigger (/compact command). Ignores threshold."""
        if not self._model:
            return None

        pruned = self.pruner.prune(messages)
        to_summarize, to_keep = self.compactor.split_messages(pruned)
        if len(to_summarize) < 2:
            return None

        if self._runtime:
            self._runtime.set_flag("isCompacting", True)
        try:
            summary_text = await self.compactor.compact(to_summarize, self._resolved_model)
            self._cached_summary = summary_text
            self._compact_up_to_index = len(messages) - len(to_keep)
            return {
                "stats": {
                    "summarized": len(to_summarize),
                    "kept": len(to_keep),
                }
            }
        finally:
            if self._runtime:
                self._runtime.set_flag("isCompacting", False)

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

    async def _restore_summary_from_store(self, thread_id: str) -> None:
        """Restore summary from SummaryStore."""
        if not thread_id:
            raise ValueError(
                "[Memory] thread_id is required for summary persistence. "
                "Ensure request.config.configurable contains 'thread_id'."
            )

        try:
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

            if self.verbose:
                print(
                    f"[Memory] Restored summary from store: "
                    f"compact_up_to_index={summary_data.compact_up_to_index}, "
                    f"compacted_at={summary_data.compacted_at}, "
                    f"is_split_turn={summary_data.is_split_turn}"
                )

        except Exception as e:
            logger.error(f"[Memory] Failed to restore summary: {e}")

    async def _rebuild_summary_from_checkpointer(self, thread_id: str) -> None:
        """Rebuild summary from checkpointer when store data is corrupted."""
        try:
            if self.verbose:
                print(f"[Memory] Rebuilding summary from checkpointer for thread {thread_id}...")

            checkpoint = self.checkpointer.get({"configurable": {"thread_id": thread_id}})
            if not checkpoint:
                if self.verbose:
                    print("[Memory] No checkpoint found, skipping rebuild")
                return

            messages = checkpoint.get("channel_values", {}).get("messages", [])
            if not messages:
                if self.verbose:
                    print("[Memory] No messages in checkpoint, skipping rebuild")
                return

            estimated = self._estimate_tokens(messages)
            if not self.compactor.should_compact(estimated, self._context_limit, self._compaction_threshold):
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
                summary_text, prefix_summary = await self.compactor.compact_with_split_turn(
                    to_summarize, turn_prefix, self._resolved_model
                )
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
