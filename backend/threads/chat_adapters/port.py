"""Agent runtime port used by web routes and chat delivery."""

from __future__ import annotations

from typing import Any

from protocols.agent_runtime import ThreadInputTransport


def get_thread_input_transport(app: Any) -> ThreadInputTransport:
    return app.state.threads_runtime_state.thread_input_transport
