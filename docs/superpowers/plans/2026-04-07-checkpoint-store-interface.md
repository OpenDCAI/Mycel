# Checkpoint Store Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate `QueryLoop` from LangGraph checkpoint payload format by introducing a thin `CheckpointStore` boundary and one LangGraph-backed adapter.

**Architecture:** Keep the current `QueryLoop` constructor stable, but route all loop persistence through a runtime-local `CheckpointStore` protocol and a `ThreadCheckpointState` dataclass. Move `channel_values` / `channel_versions` / `create_checkpoint(...)` ownership into a LangGraph adapter without touching `MemoryMiddleware`.

**Tech Stack:** Python, asyncio, dataclasses, pytest, pyright, ruff

---

### Task 1: Lock the new loop boundary with a failing test

**Files:**
- Modify: `tests/Unit/core/test_loop.py`
- Read: `core/runtime/loop.py`

- [ ] **Step 1: Write the failing test**

Add one unit that proves `QueryLoop` saves through a store boundary instead of constructing LangGraph payloads itself.

Expected shape:

```python
class _RecordingCheckpointStore:
    def __init__(self):
        self.saved: list[tuple[str, ThreadCheckpointState]] = []

    async def load(self, thread_id: str):
        return None

    async def save(self, thread_id: str, state: ThreadCheckpointState) -> None:
        self.saved.append((thread_id, state))


@pytest.mark.asyncio
async def test_query_loop_saves_thread_state_via_checkpoint_store():
    store = _RecordingCheckpointStore()
    loop = make_loop(mock_model_no_tools(), app_state=AppState(), runtime=SimpleNamespace(cost=0.0))
    loop._checkpoint_store = store

    await loop._save_messages("thread-1", [HumanMessage(content="hi")])

    assert len(store.saved) == 1
    assert store.saved[0][0] == "thread-1"
    assert store.saved[0][1].messages
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
uv run pytest tests/Unit/core/test_loop.py -k 'saves_thread_state_via_checkpoint_store' -q
```

Expected: FAIL because `QueryLoop` does not yet expose the store seam.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/Unit/core/test_loop.py
git commit -m "test: lock checkpoint store seam"
```

### Task 2: Add the runtime-local checkpoint contract

**Files:**
- Create: `core/runtime/checkpoint_store.py`
- Modify: `tests/Unit/core/test_loop.py`

- [ ] **Step 1: Add the thread-state dataclass and protocol**

Create `core/runtime/checkpoint_store.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ThreadCheckpointState:
    messages: list
    tool_permission_context: dict[str, Any]
    pending_permission_requests: dict[str, dict[str, Any]]
    resolved_permission_requests: dict[str, dict[str, Any]]
    memory_compaction_state: dict[str, Any]
    mcp_instruction_state: dict[str, Any]


class CheckpointStore(Protocol):
    async def load(self, thread_id: str) -> ThreadCheckpointState | None: ...
    async def save(self, thread_id: str, state: ThreadCheckpointState) -> None: ...
```

- [ ] **Step 2: Update the new unit test imports**

Import `ThreadCheckpointState` in `tests/Unit/core/test_loop.py` and keep the recording fake fully typed.

- [ ] **Step 3: Run the focused test**

Run:

```bash
uv run pytest tests/Unit/core/test_loop.py -k 'saves_thread_state_via_checkpoint_store' -q
```

Expected: still RED, but only because `QueryLoop` has not been switched yet.

- [ ] **Step 4: Commit the new contract file**

```bash
git add core/runtime/checkpoint_store.py tests/Unit/core/test_loop.py
git commit -m "feat: add runtime checkpoint store contract"
```

### Task 3: Move LangGraph shape into one adapter

**Files:**
- Create: `core/runtime/langgraph_checkpoint_store.py`
- Read: `core/runtime/loop.py`

- [ ] **Step 1: Create the adapter shell**

Create `LangGraphCheckpointStore` that wraps the current saver object and owns checkpoint config creation plus LangGraph imports.

Expected skeleton:

```python
class LangGraphCheckpointStore:
    def __init__(self, saver: Any):
        self._saver = saver

    async def load(self, thread_id: str) -> ThreadCheckpointState | None:
        ...

    async def save(self, thread_id: str, state: ThreadCheckpointState) -> None:
        ...
```

- [ ] **Step 2: Move read-side shape parsing into the adapter**

Port the existing checkpoint load behavior:

- `aget(...)`
- `channel_values`
- missing checkpoint -> `None`

- [ ] **Step 3: Move write-side shape/version logic into the adapter**

Port the existing logic for:

- `empty_checkpoint(...)`
- existing checkpoint normalization
- `create_checkpoint(...)`
- `channel_versions`
- `updated_channels`
- metadata for `aput(...)`

- [ ] **Step 4: Run targeted static checks on the new modules**

Run:

```bash
uv run pyright core/runtime/checkpoint_store.py core/runtime/langgraph_checkpoint_store.py
uv run ruff check core/runtime/checkpoint_store.py core/runtime/langgraph_checkpoint_store.py
uv run ruff format --check core/runtime/checkpoint_store.py core/runtime/langgraph_checkpoint_store.py
```

Expected: `0 errors` and all green.

- [ ] **Step 5: Commit the adapter extraction**

```bash
git add core/runtime/checkpoint_store.py core/runtime/langgraph_checkpoint_store.py
git commit -m "refactor: extract langgraph checkpoint store adapter"
```

### Task 4: Switch `QueryLoop` to the store boundary

**Files:**
- Modify: `core/runtime/loop.py`
- Modify: `tests/Unit/core/test_loop.py`

- [ ] **Step 1: Add store wiring to `QueryLoop`**

Keep constructor compatibility, but route raw saver input into the adapter:

```python
self.checkpointer = checkpointer
self._checkpoint_store = (
    LangGraphCheckpointStore(checkpointer) if checkpointer is not None else None
)
```

If a dedicated `checkpoint_store` constructor arg is added, keep it optional and local to this file. Do not start a wide constructor cascade in the same task.

- [ ] **Step 2: Replace raw load/save calls**

Update:

- `_load_messages(...)`
- `_hydrate_thread_state_from_checkpoint(...)`
- `_save_messages(...)`

So they operate on `ThreadCheckpointState` and no longer import LangGraph checkpoint helpers.

- [ ] **Step 3: Remove loop-local LangGraph checkpoint formatting**

Delete or move out of `loop.py`:

- `_normalize_checkpoint_for_write(...)`
- loop-local metadata/version shaping
- direct `channel_values` parsing/writing

Only keep runtime-state assembly and restore logic in the loop.

- [ ] **Step 4: Run focused loop tests**

Run:

```bash
uv run pytest tests/Unit/core/test_loop.py -k 'checkpoint or aget_state or saves_thread_state_via_checkpoint_store' -q
```

Expected: PASS

- [ ] **Step 5: Commit the loop cutover**

```bash
git add core/runtime/loop.py tests/Unit/core/test_loop.py
git commit -m "refactor: route query loop through checkpoint store"
```

### Task 5: Prove no caller-visible regression and hold the stopline

**Files:**
- Read: `tests/Integration/test_query_loop_backend_bridge.py`
- Read: `core/runtime/middleware/memory/middleware.py`

- [ ] **Step 1: Run one integration seed**

Run:

```bash
uv run pytest tests/Integration/test_query_loop_backend_bridge.py -k 'persist or history or permission_state' -q
```

Expected: PASS

- [ ] **Step 2: Run touched static checks**

Run:

```bash
uv run pyright core/runtime/loop.py core/runtime/checkpoint_store.py core/runtime/langgraph_checkpoint_store.py tests/Unit/core/test_loop.py
uv run ruff check core/runtime/loop.py core/runtime/checkpoint_store.py core/runtime/langgraph_checkpoint_store.py tests/Unit/core/test_loop.py
uv run ruff format --check core/runtime/loop.py core/runtime/checkpoint_store.py core/runtime/langgraph_checkpoint_store.py tests/Unit/core/test_loop.py
```

Expected: `0 errors` and all green.

- [ ] **Step 3: Confirm the stopline**

Do **not** modify `core/runtime/middleware/memory/middleware.py` in this checkpoint, even though it still has direct checkpointer shape knowledge. Record it as the next seam instead of mixing it into this plan.

- [ ] **Step 4: Commit the completed checkpoint**

```bash
git add core/runtime/loop.py core/runtime/checkpoint_store.py core/runtime/langgraph_checkpoint_store.py tests/Unit/core/test_loop.py
git commit -m "refactor: isolate loop from langgraph checkpoint format"
```
