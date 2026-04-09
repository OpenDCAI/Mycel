# Supabase-First Runtime Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Supabase-first runtime path explicit and authoritative before continuing provider-parity cuts.

**Architecture:** Current `origin/dev` already has two layers: a Supabase-only `StorageContainer` and a `storage.runtime.build_storage_container(...)` entry point. The first implementation slice should not invent a third abstraction. It should make `storage.runtime` the single runtime entry and route the web composition root through it, while preserving current repo wiring and public-client islands.

**Tech Stack:** Python, FastAPI lifespan wiring, Supabase repo providers, pytest

---

### Task 1: Checkpoint + Plan Alignment

**Files:**
- Modify: `teams/tasks/supabase-first-runtime-parity/_index.md`
- Modify: `teams/tasks/supabase-first-runtime-parity/subtask-01-supabase-boot-contract.md`
- Create: `teams/doc/core/2026-04-09-supabase-first-runtime-parity-plan.md`

- [ ] **Step 1: Record the current first-slice ruling**

Add a short ruling that the first implementation slice is `strategy entry alignment`, not full provider parity.

- [ ] **Step 2: Carry forward the boot-contract evidence**

Copy the caller-proven Supabase boot findings into `subtask-01-supabase-boot-contract.md` so the implementation branch carries the latest evidence.

- [ ] **Step 3: Save this plan**

Keep the plan in `teams/doc/core/2026-04-09-supabase-first-runtime-parity-plan.md`.

### Task 2: Write the Failing Tests for Runtime Entry Alignment

**Files:**
- Modify: `tests/Unit/storage/test_runtime_builder_contract.py`
- Modify: `tests/Integration/test_storage_repo_abstraction_unification.py`

- [ ] **Step 1: Add a unit test for public-client passthrough on `build_storage_container(...)`**

Add a test that calls:

```python
container = storage_runtime.build_storage_container(
    supabase_client=runtime_client,
    public_supabase_client=public_client,
)
repo = container.panel_task_repo()
```

and asserts the repo is built from `public_client`, not `runtime_client`.

- [ ] **Step 2: Add an integration test that `lifespan` uses `storage.runtime.build_storage_container`**

Monkeypatch:

```python
monkeypatch.setattr("storage.runtime.build_storage_container", _fake_build_storage_container)
```

then assert `lifespan` wires `app.state.user_repo`, `thread_repo`, `lease_repo`, `panel_task_repo`, etc. from the returned container.

- [ ] **Step 3: Run the targeted tests to verify red/green behavior**

Run:

```bash
uv run pytest -q tests/Unit/storage/test_runtime_builder_contract.py tests/Integration/test_storage_repo_abstraction_unification.py -k 'build_storage_container or lifespan_wires_user_and_thread_repos_from_storage_runtime_container'
```

Expected:
- initially fails until implementation is updated
- then passes after the minimal change

### Task 3: Minimal Implementation

**Files:**
- Modify: `backend/web/core/lifespan.py`
- Modify: `storage/runtime.py`

- [ ] **Step 1: Route `lifespan` through the runtime entry**

Replace direct `StorageContainer(...)` construction in `lifespan.py` with:

```python
from storage.runtime import build_storage_container

storage_container = build_storage_container(
    supabase_client=_supabase_client,
    public_supabase_client=_public_supabase_client,
)
```

- [ ] **Step 2: Keep runtime entry explicit about both clients**

Ensure `storage.runtime.build_storage_container(...)` remains the single authoritative runtime constructor and passes both:

```python
StorageContainer(
    supabase_client=client,
    public_supabase_client=public_client,
)
```

- [ ] **Step 3: Do not widen provider parity in this slice**

Leave SQLite residual callers alone in this task:
- `backend/web/services/file_channel_service.py`
- `sandbox/chat_session.py`
- `sandbox/lease.py`
- `sandbox/manager.py`
- `core/runtime/middleware/queue/manager.py`
- `core/runtime/middleware/memory/summary_store.py`

### Task 4: Verification

**Files:**
- No additional file changes required

- [ ] **Step 1: Run focused unit/integration tests**

Run:

```bash
uv run pytest -q tests/Unit/storage/test_runtime_builder_contract.py tests/Integration/test_storage_repo_abstraction_unification.py
```

Expected:
- all selected tests pass

- [ ] **Step 2: Run lint + py_compile on touched files**

Run:

```bash
uv run ruff check storage/runtime.py backend/web/core/lifespan.py tests/Unit/storage/test_runtime_builder_contract.py tests/Integration/test_storage_repo_abstraction_unification.py
uv run python -m py_compile storage/runtime.py backend/web/core/lifespan.py tests/Unit/storage/test_runtime_builder_contract.py tests/Integration/test_storage_repo_abstraction_unification.py
```

Expected:
- `All checks passed!`
- `exit 0`

- [ ] **Step 3: Record the next slice**

Update the task ledger with the result of this cut and nominate the next bounded move:
- either `service surface parity`
- or a narrower `runtime-side-store alignment` cut if the test evidence points there
