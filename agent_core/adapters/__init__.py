"""Default standalone adapters for the agent_core ports.

These let the core run with zero external infrastructure (no DB, no web server,
no message bus). Hosts that need durability or delivery (e.g. Mycel's Postgres
checkpoint store + SSE event bus) supply their own adapters implementing the
same ports.
"""

from __future__ import annotations

from agent_core.adapters.memory_checkpoint import InMemoryCheckpointStore
from agent_core.adapters.null_emitter import NullEventBus

__all__ = ["InMemoryCheckpointStore", "NullEventBus"]
