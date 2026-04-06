# Checkpoint Store Interface Design

**Date:** 2026-04-07
**Branch:** `dev`

## Goal

Extract a thin `CheckpointStore` boundary so `QueryLoop` stops constructing and parsing LangGraph checkpoint payloads directly.

This slice is about ownership and format isolation, not changing persistence behavior.

## Scope

This design covers:

- `core/runtime/loop.py`
- a new runtime-local checkpoint store boundary
- a LangGraph-backed adapter that owns `channel_values` / version metadata shape
- focused `tests/Unit/core/test_loop.py` coverage for the new boundary

This design does **not** cover:

- `core/runtime/middleware/memory/middleware.py`
- removing `langgraph` from the repo today
- changing `LeonAgent` checkpointer bringup rules
- changing persisted thread state fields
- changing checkpoint storage backends

## Current Facts

### 1. `QueryLoop` still knows LangGraph's storage shape

Current `core/runtime/loop.py` does all of the following itself:

- imports `create_checkpoint`, `empty_checkpoint`, `CheckpointMetadata`
- reads `checkpoint["channel_values"]`
- writes `checkpoint["channel_values"]`
- computes `channel_versions`
- emits `updated_channels`

That means the loop owns both runtime behavior **and** LangGraph persistence format.

### 2. The thread state contract is already smaller than LangGraph's checkpoint

The loop only really cares about one thread-scoped state bundle:

- `messages`
- `tool_permission_context`
- `pending_permission_requests`
- `resolved_permission_requests`
- `memory_compaction_state`
- `mcp_instruction_state`

Everything else in the LangGraph checkpoint is storage-level machinery, not loop policy.

### 3. There is one adjacent seam that should stay out of this slice

`core/runtime/middleware/memory/middleware.py` still has `_rebuild_summary_from_checkpointer(...)` and reaches into `channel_values` directly.

That is a real follow-up seam, but it is not the same owner boundary as `QueryLoop`. Pulling both into one change would turn a bounded runtime refactor into a broader memory/persistence rewrite.

## Problem

Right now `QueryLoop` has to understand two different things at once:

1. what thread state it wants to persist
2. how LangGraph savers expect checkpoints to be shaped and versioned

That has three costs:

- loop code is still tied to `langgraph.checkpoint.base`
- saver-specific normalization/version logic lives in runtime behavior code
- swapping persistence format later would require editing the loop again

The current code works, but the format owner is still wrong.

## Chosen Approach

Add a thin runtime-local `CheckpointStore` protocol plus a LangGraph-backed adapter.

`QueryLoop` should speak in terms of thread state only:

- `load(thread_id) -> ThreadCheckpointState | None`
- `save(thread_id, state) -> None`

Only the LangGraph adapter should know about:

- `checkpoint_ns`
- `channel_values`
- `channel_versions`
- `updated_channels`
- `create_checkpoint(...)`
- `empty_checkpoint(...)`

## Intended Backend Shape

### 1. Add a runtime-local thread state object

Create one small dataclass, for example:

```python
@dataclass(frozen=True)
class ThreadCheckpointState:
    messages: list
    tool_permission_context: dict[str, Any]
    pending_permission_requests: dict[str, dict[str, Any]]
    resolved_permission_requests: dict[str, dict[str, Any]]
    memory_compaction_state: dict[str, Any]
    mcp_instruction_state: dict[str, Any]
```

This is the honest contract the loop already consumes.

### 2. Add a protocol

Create a small protocol in a runtime-local module:

```python
class CheckpointStore(Protocol):
    async def load(self, thread_id: str) -> ThreadCheckpointState | None: ...
    async def save(self, thread_id: str, state: ThreadCheckpointState) -> None: ...
```

This is intentionally minimal. Do not grow it into a generic repository abstraction in this slice.

### 3. Move LangGraph shape into one adapter

Create a LangGraph-backed adapter, for example `LangGraphCheckpointStore`, that wraps the existing saver object.

That adapter should own:

- checkpoint config construction
- checkpoint-shape normalization
- reading `channel_values`
- version advancement when saver exposes `get_next_version`
- metadata creation for `aput(...)`

The adapter should preserve the current write semantics exactly.

### 4. Keep `QueryLoop` constructor stable

Do not force a wide constructor cascade through `LeonAgent` in this slice.

Recommended shape:

- keep accepting `checkpointer` today
- build a `LangGraphCheckpointStore` inside `QueryLoop` when a raw saver is supplied
- store it on something like `self._checkpoint_store`

That keeps the public surface stable while moving format ownership out of the loop.

### 5. Move loop methods up to the thread-state level

After the split:

- `_load_messages(...)` should load `ThreadCheckpointState`
- `_hydrate_thread_state_from_checkpoint(...)` should read from `ThreadCheckpointState`
- `_save_messages(...)` should build one `ThreadCheckpointState` and hand it to the store

`QueryLoop` should stop importing LangGraph checkpoint helpers entirely.

## Non-Goals

- Do not refactor `MemoryMiddleware` in the same change
- Do not introduce fallback stores
- Do not redesign the persisted thread state fields
- Do not change startup/checkpointer bringup rules
- Do not remove the raw `checkpointer` constructor arg yet if that would force a bigger cascade

## Testing Strategy

### Required proof

- one red/green unit that proves `QueryLoop` now delegates checkpoint persistence through a store boundary
- existing loop checkpoint tests stay green
- one integration seed using the in-memory checkpointer stays green

### Good proof candidates

- `tests/Unit/core/test_loop.py`
  - save/load through a fake `CheckpointStore`
  - existing `aget_state` and persistence tests
- `tests/Integration/test_query_loop_backend_bridge.py`
  - one seed that proves backend-facing state hydration still works

### Out-of-scope failures

If a `LeonAgent` integration test still fails earlier on missing Supabase env, that is bringup debt, not evidence against this checkpoint boundary.

## Stopline

This slice stops when:

- `QueryLoop` no longer imports LangGraph checkpoint helpers
- `QueryLoop` persists and hydrates through `CheckpointStore`
- LangGraph checkpoint shape lives in one adapter
- focused loop tests stay green

It must **not** expand into:

- memory middleware refactors
- storage backend swaps
- checkpointer startup contract work
- generic storage-abstraction cleanup across the repo
