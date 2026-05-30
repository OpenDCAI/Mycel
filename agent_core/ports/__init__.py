"""Ports — the abstractions the core depends on, defined as Protocols/ABCs.

The core talks only to these interfaces. Concrete implementations live in
``agent_core.adapters`` (standalone defaults) or are supplied by the host
application (e.g. Mycel's Postgres checkpoint store, SSE event bus).
"""

from __future__ import annotations

from agent_core.ports.checkpoint import CheckpointStore, ThreadCheckpointState
from agent_core.ports.event_bus import EventBusPort, EventEmitter

__all__ = [
    "CheckpointStore",
    "EventBusPort",
    "EventEmitter",
    "ThreadCheckpointState",
]
