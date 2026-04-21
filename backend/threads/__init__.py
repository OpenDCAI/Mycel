"""Threads domain — agent-side execution.

Aggregate root: `thread`. Subordinate entities: `run`, `run_event`,
`checkpoint`, runtime binding, runtime state.

IN:
    - Threads, runs, run events, checkpoints
    - Runtime bindings and runtime state
    - Sandbox resolution per thread (which lease binds, not how provisioned)
    - Chat adapters (chat -> runtime, runtime -> chat) in chat_adapters/
    - Thread history projection for chat
    - Thread launch configuration and visibility
    - Thread input interruption
    - Streaming / SSE loop for thread-scoped events (streaming.py)
    - Runtime instance pool (pool/)
    - Thread display state builder (display/)
    - Thread-scoped pub/sub event bus (event_bus.py)
    - Thread-bound workspace file channel (file_channel.py)
    - Message payload helpers (message_content.py)

OUT:
    - Chat domain semantics (owned by messaging/, backend/chat/)
    - Sandbox provider mechanics (owned by sandbox/, backend/sandboxes/)
    - User identity & auth (owned by backend/identity/)
    - HTTP edge composition (owned by backend/web/)
    - Monitor-side projections (owned by backend/monitor/)

Canonical protocols consumed/implemented:
    - implements protocols.runtime_read.RuntimeThreadActivityReader
      (via chat_adapters/activity_reader.py)
    - produces/consumes protocols.agent_runtime.* dispatch envelopes
      (via chat_adapters/gateway.py, chat_adapters/port.py)

Deep dependencies:
    top-level: core/, sandbox/, storage/, messaging/, protocols/, config/
    backend:   identity/, sandboxes/

See program/doc/core/backend-package-dependencies-2026-04-20.md §5.4
for the full charter. See backend-domain-target-architecture-2026-04-19.md
§3.2 and §4 for the aggregate-root rationale.
"""
