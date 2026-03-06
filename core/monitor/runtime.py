"""Agent 运行时状态聚合"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

from .context_monitor import ContextMonitor
from .state_monitor import AgentFlags, AgentState, StateMonitor
from .token_monitor import TokenMonitor


class AgentRuntime:
    """聚合所有 Monitor 的数据，提供统一的状态访问接口"""

    def __init__(
        self,
        token_monitor: TokenMonitor,
        context_monitor: ContextMonitor,
        state_monitor: StateMonitor,
    ):
        self.token = token_monitor
        self.context = context_monitor
        self.state = state_monitor
        self._subagent_event_buffer: dict[str, list[dict[str, Any]]] = {}  # tool_call_id -> events
        self._event_callback: Callable[[dict], None] | None = None
        self._activity_sink: Callable[[dict], Any] | None = None

    # ========== 状态代理 ==========

    @property
    def current_state(self) -> AgentState:
        return self.state.state

    @property
    def flags(self) -> AgentFlags:
        return self.state.flags

    def transition(self, new_state: AgentState) -> bool:
        return self.state.transition(new_state)

    def set_flag(self, name: str, value: bool) -> None:
        self.state.set_flag(name, value)

    def can_accept_task(self) -> bool:
        return self.state.can_accept_task()

    def is_running(self) -> bool:
        return self.state.is_running()

    # ========== Token 代理 ==========

    @property
    def total_tokens(self) -> int:
        return self.token.total_tokens

    @property
    def input_tokens(self) -> int:
        return self.token.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.token.output_tokens

    @property
    def reasoning_tokens(self) -> int:
        return self.token.reasoning_tokens

    @property
    def cache_read_tokens(self) -> int:
        return self.token.cache_read_tokens

    @property
    def cache_write_tokens(self) -> int:
        return self.token.cache_write_tokens

    # 向后兼容
    @property
    def prompt_tokens(self) -> int:
        return self.token.prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self.token.completion_tokens

    # ========== 成本代理 ==========

    @property
    def cost(self) -> float:
        """当前累计成本（USD）"""
        return float(self.token.get_cost().get("total", 0))

    # ========== 上下文代理 ==========

    @property
    def message_count(self) -> int:
        return self.context.message_count

    @property
    def estimated_context_tokens(self) -> int:
        return self.context.estimated_tokens

    def is_context_near_limit(self) -> bool:
        return self.context.is_near_limit()

    # ========== 聚合输出 ==========

    def get_status_dict(self) -> dict[str, Any]:
        """返回完整状态字典"""
        return {
            "state": self.state.get_metrics(),
            "tokens": self.token.get_metrics(),
            "context": self.context.get_metrics(),
        }

    def get_status_line(self) -> str:
        """返回单行状态，用于 TUI 状态栏"""
        parts = [f"[{self.current_state.value.upper()}]"]

        flag_names = [
            ("isStreaming", "streaming"),
            ("isCompacting", "compacting"),
            ("isWaiting", "waiting"),
            ("isBlocked", "blocked"),
            ("hasError", "error"),
        ]
        for flag_attr, label in flag_names:
            if getattr(self.flags, flag_attr):
                parts.append(label)

        if self.total_tokens > 0:
            parts.append(f"tokens:{self.total_tokens}")

        if self.cost > 0:
            parts.append(f"${self.cost:.2f}")

        ctx = self.context.get_metrics()
        if ctx["usage_percent"] > 0:
            parts.append(f"ctx:{ctx['usage_percent']:.0f}%")

        return " | ".join(parts)

    # ========== Event callback ==========

    def set_event_callback(self, callback: Callable[[dict], None] | None) -> None:
        """Set real-time event callback. Used by streaming_service."""
        self._event_callback = callback

    def set_activity_sink(self, sink: Callable[[dict], Any] | None) -> None:
        """Set persistent activity event sink. Unlike _event_callback, this survives across runs."""
        self._activity_sink = sink

    def bind_thread(self, activity_sink: Callable[[dict], Any]) -> None:
        """Set per-thread activity sink. Idempotent — safe to call on every run."""
        self._activity_sink = activity_sink

    def unbind_thread(self) -> None:
        """Clear per-thread handlers on thread deletion."""
        self._activity_sink = None

    def _dispatch_to_sink(self, event: dict[str, Any]) -> None:
        """Fire-and-forget dispatch to persistent activity sink."""
        if not self._activity_sink:
            return
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._activity_sink(event))
            task.add_done_callback(self._handle_sink_error)
        except RuntimeError:
            pass  # No event loop running (e.g., during shutdown)

    @staticmethod
    def _handle_sink_error(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("Activity sink failed: %s", exc)

    def emit_activity_event(self, event: dict[str, Any]) -> None:
        """Emit activity event (command progress, background task, etc).

        Mutual exclusion: when _event_callback is set (run active), dispatch
        only via callback (which feeds activity_queue → drain loop → emit() →
        ThreadEventBuffer + SQLite). When no callback (run ended), dispatch
        via _activity_sink directly to ThreadEventBuffer.
        """
        if self._event_callback:
            self._event_callback(event)
        else:
            self._dispatch_to_sink(event)

    # ========== Sub-agent event dispatch ==========

    def emit_subagent_event(
        self,
        parent_tool_call_id: str,
        event: dict[str, Any],
        *,
        background: bool = False,
    ) -> None:
        """Emit sub-agent event with routing metadata.

        Injects parent_tool_call_id into the data payload for correlation.
        """
        try:
            data = json.loads(event.get("data", "{}"))
        except (json.JSONDecodeError, TypeError):
            data = {}
        data["parent_tool_call_id"] = parent_tool_call_id
        if background:
            data["background"] = True
        enriched_event = {
            "event": event.get("event", ""),
            "data": json.dumps(data, ensure_ascii=False),
        }

        # Same mutual exclusion as emit_activity_event
        if self._event_callback:
            self._event_callback(enriched_event)
        else:
            self._dispatch_to_sink(enriched_event)
            # Batch fallback (backward compat for TUI / non-SSE callers)
            self._subagent_event_buffer.setdefault(parent_tool_call_id, []).append(enriched_event)

    def get_pending_subagent_events(self) -> list[tuple[str, list[dict[str, Any]]]]:
        """Get and clear pending sub-agent events."""
        events = list(self._subagent_event_buffer.items())
        self._subagent_event_buffer.clear()
        return events
