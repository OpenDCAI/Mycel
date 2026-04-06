# Memory Middleware Checkpoint Store Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align `MemoryMiddleware` with the runtime-local checkpoint store boundary and preserve late-bound checkpointer wiring in async agent bringup.

**Architecture:** Keep the current memory compaction behavior intact, but stop `MemoryMiddleware` from reaching into raw saver checkpoint shape. Reuse the existing `LangGraphCheckpointStore` adapter for read-side message recovery and ensure `LeonAgent.ainit()` pushes the late-created checkpointer into both `QueryLoop` and `MemoryMiddleware`.

**Tech Stack:** Python, asyncio, pytest, pyright, ruff

---

### Task 1: Lock the late-bound memory seam with failing integration tests

**Files:**
- Modify: `tests/Integration/test_memory_middleware_integration.py`
- Modify: `tests/Integration/test_leon_agent.py`
- Read: `core/runtime/middleware/memory/middleware.py`
- Read: `core/runtime/agent.py`

- [ ] **Step 1: Write a failing memory middleware test**

Add one focused test that sets `middleware.checkpointer` after construction using an async-only saver (`aget`/`aput`, no sync `get`) and calls `_rebuild_summary_from_checkpointer(...)`.

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
uv run pytest tests/Integration/test_memory_middleware_integration.py -k 'late_bound_async_checkpointer' -q
```

Expected: FAIL because `_rebuild_summary_from_checkpointer(...)` still calls `checkpointer.get(...)`.

- [ ] **Step 3: Write a failing LeonAgent wiring test**

Add one integration test that patches `LeonAgent._init_checkpointer()` to set a fake checkpointer during `await agent.ainit()`, then asserts `agent._memory_middleware.checkpointer` is the same object.

- [ ] **Step 4: Run the focused agent test to verify RED**

Run:

```bash
uv run pytest tests/Integration/test_leon_agent.py -k 'pushes_late_checkpointer_into_memory_middleware' -q
```

Expected: FAIL because `ainit()` only updates `QueryLoop`.

### Task 2: Route memory rebuild through the checkpoint store adapter

**Files:**
- Modify: `core/runtime/middleware/memory/middleware.py`
- Read: `core/runtime/checkpoint_store.py`
- Read: `core/runtime/langgraph_checkpoint_store.py`

- [ ] **Step 1: Add store-backed checkpointer wiring**

Give `MemoryMiddleware` the same post-init shape as `QueryLoop`:

- `self.checkpointer = checkpointer` in `__init__`
- a `checkpointer` property that rebuilds `self._checkpoint_store`
- `_checkpoint_store: CheckpointStore | None`

- [ ] **Step 2: Replace raw saver reads in `_rebuild_summary_from_checkpointer(...)`**

Load `ThreadCheckpointState` through the adapter and read only `state.messages`.

- [ ] **Step 3: Keep the stopline**

Do not redesign compaction rules, summary persistence, or `SummaryStore`. This slice is only about checkpoint ownership and late wiring.

### Task 3: Push late checkpointer wiring through `LeonAgent.ainit()`

**Files:**
- Modify: `core/runtime/agent.py`
- Read: `core/runtime/middleware/memory/middleware.py`

- [ ] **Step 1: Update async bringup wiring**

After `await self._init_checkpointer()`, keep the existing:

```python
self.agent.checkpointer = self.checkpointer
```

and add the matching memory update:

```python
if hasattr(self, "_memory_middleware"):
    self._memory_middleware.checkpointer = self.checkpointer
```

- [ ] **Step 2: Do not widen the constructor cascade**

Do not add new public constructor args here. Keep the fix local to `MemoryMiddleware` + `LeonAgent.ainit()`.

### Task 4: Verify the slice and stop

**Files:**
- Modify: `tests/Integration/test_memory_middleware_integration.py`
- Modify: `tests/Integration/test_leon_agent.py`

- [ ] **Step 1: Run focused integration proofs**

Run:

```bash
uv run pytest tests/Integration/test_memory_middleware_integration.py -k 'late_bound_async_checkpointer or rebuild_from_checkpointer or checkpointer_unavailable_graceful_degradation' -q
uv run pytest tests/Integration/test_leon_agent.py -k 'pushes_late_checkpointer_into_memory_middleware or persists_summary_store_after_second_turn_compaction' -q
```

Expected: PASS

- [ ] **Step 2: Run touched static checks**

Run:

```bash
uv run pyright core/runtime/middleware/memory/middleware.py core/runtime/agent.py tests/Integration/test_memory_middleware_integration.py tests/Integration/test_leon_agent.py
uv run ruff check core/runtime/middleware/memory/middleware.py core/runtime/agent.py tests/Integration/test_memory_middleware_integration.py tests/Integration/test_leon_agent.py
uv run ruff format --check core/runtime/middleware/memory/middleware.py core/runtime/agent.py tests/Integration/test_memory_middleware_integration.py tests/Integration/test_leon_agent.py
```

Expected: all green

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-04-07-memory-middleware-checkpoint-store-followup.md core/runtime/middleware/memory/middleware.py core/runtime/agent.py tests/Integration/test_memory_middleware_integration.py tests/Integration/test_leon_agent.py
git commit -m "refactor: align memory middleware with checkpoint store"
```
