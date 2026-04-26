import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .base import BaseMonitor

logger = logging.getLogger(__name__)


class AgentState(Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    ACTIVE = "active"
    IDLE = "idle"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"
    ERROR = "error"
    RECOVERING = "recovering"


@dataclass
class AgentFlags:
    is_streaming: bool = False
    is_compacting: bool = False
    is_waiting: bool = False
    is_blocked: bool = False
    can_interrupt: bool = True
    has_error: bool = False
    needs_recovery: bool = False


VALID_TRANSITIONS = {
    AgentState.INITIALIZING: [AgentState.READY, AgentState.ERROR],
    AgentState.READY: [AgentState.ACTIVE, AgentState.TERMINATED],
    AgentState.ACTIVE: [AgentState.IDLE, AgentState.SUSPENDED, AgentState.ERROR],
    AgentState.IDLE: [AgentState.ACTIVE, AgentState.TERMINATED],
    AgentState.SUSPENDED: [AgentState.ACTIVE, AgentState.TERMINATED],
    AgentState.ERROR: [AgentState.RECOVERING, AgentState.TERMINATED],
    AgentState.RECOVERING: [AgentState.READY, AgentState.TERMINATED],
    AgentState.TERMINATED: [],
}


class StateMonitor(BaseMonitor):
    def __init__(self):
        self.state = AgentState.INITIALIZING
        self.flags = AgentFlags()
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.last_error_type: str | None = None
        self.last_error_message: str | None = None
        self.last_error_at: datetime | None = None
        self._callbacks: list[Callable[[AgentState, AgentState], None]] = []
        self._transition_lock = threading.Lock()

    def on_request(self, request: dict[str, Any]) -> None:
        self.last_activity = datetime.now()

    def on_response(self, request: dict[str, Any], response: dict[str, Any]) -> None:
        self.last_activity = datetime.now()

    def transition(self, new_state: AgentState) -> bool:
        with self._transition_lock:
            if new_state in VALID_TRANSITIONS.get(self.state, []):
                old_state = self.state
                self.state = new_state
            else:
                return False
        # Fire callbacks outside lock to avoid deadlock
        self._emit_state_changed(old_state, new_state)
        return True

    def set_flag(self, name: str, value: bool) -> None:
        if hasattr(self.flags, name):
            setattr(self.flags, name, value)

    def on_state_changed(self, callback: Callable[[AgentState, AgentState], None]) -> None:
        self._callbacks.append(callback)

    def _emit_state_changed(self, old: AgentState, new: AgentState) -> None:
        for cb in self._callbacks:
            try:
                cb(old, new)
            except Exception:
                logger.exception("State transition callback failed: %s -> %s", old.value, new.value)

    def mark_ready(self) -> bool:
        return self.transition(AgentState.READY)

    def mark_error(self, error: Exception | None = None) -> bool:
        self.flags.has_error = True
        if error is not None:
            # @@@error-snapshot - Capture a small, inspectable error snapshot for debugging.
            self.last_error_type = type(error).__name__
            msg = str(error)
            self.last_error_message = msg[:500] if msg else ""
            self.last_error_at = datetime.now()

        # When an exception happens mid-run (ACTIVE), moving into a sticky ERROR state prevents any new runs
        # and causes misleading 409 "already running" responses. Keep the agent runnable but surface hasError
        # + last_error_* via metrics for debugging.
        if self.state == AgentState.ACTIVE:
            return self.transition(AgentState.IDLE)

        return self.transition(AgentState.ERROR)

    def mark_terminated(self) -> bool:
        if self.state == AgentState.ACTIVE:
            self.transition(AgentState.IDLE)

        if self.state in (AgentState.READY, AgentState.IDLE, AgentState.SUSPENDED, AgentState.ERROR):
            return self.transition(AgentState.TERMINATED)

        return False

    def can_accept_task(self) -> bool:
        return self.state in (AgentState.READY, AgentState.IDLE)

    def is_running(self) -> bool:
        return self.state == AgentState.ACTIVE

    def get_metrics(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "flags": {
                "streaming": self.flags.is_streaming,
                "compacting": self.flags.is_compacting,
                "waiting": self.flags.is_waiting,
                "blocked": self.flags.is_blocked,
                "error": self.flags.has_error,
            },
            "error": {
                "type": self.last_error_type,
                "message": self.last_error_message,
                "at": self.last_error_at.isoformat() if self.last_error_at else None,
            },
            "uptime_seconds": round((datetime.now() - self.created_at).total_seconds(), 1),
            "last_activity": self.last_activity.isoformat(),
        }

    def reset(self) -> None:
        self.state = AgentState.INITIALIZING
        self.flags = AgentFlags()
        self.last_error_type = None
        self.last_error_message = None
        self.last_error_at = None
