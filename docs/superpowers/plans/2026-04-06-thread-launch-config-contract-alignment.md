# Thread Launch Config Contract Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make thread launch config a single owned contract in `thread_launch_config_service.py`, and prove it with focused tests.

**Architecture:** Extract the successful launch-config payload shape behind explicit service helpers, keep router branch selection local, and verify that persisted confirmed/successful configs still normalize to the same contract.

**Tech Stack:** FastAPI, pytest, plain service helpers

---

### Task 1: Write focused launch-config regressions

**Files:**
- Create: `tests/Fix/test_thread_launch_config_contract.py`
- Read: `backend/web/services/thread_launch_config_service.py`
- Read: `backend/web/routers/threads.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_save_last_confirmed_config_normalizes_payload():
    ...

def test_build_existing_launch_config_uses_canonical_shape():
    ...

def test_build_new_launch_config_normalizes_recipe_snapshot():
    ...

@pytest.mark.asyncio
async def test_create_thread_persists_existing_lease_successful_config():
    ...

@pytest.mark.asyncio
async def test_create_thread_persists_new_launch_successful_config():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/Fix/test_thread_launch_config_contract.py -q`
Expected: FAIL because the helper builders do not exist yet and the router still owns the successful-config dict shape.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/Fix/test_thread_launch_config_contract.py
git commit -m "test: cover thread launch config contract"
```

### Task 2: Move successful payload construction into the service

**Files:**
- Modify: `backend/web/services/thread_launch_config_service.py`
- Modify: `backend/web/routers/threads.py`

- [ ] **Step 1: Add explicit builder helpers in the service**

```python
def build_existing_launch_config(*, provider_config: str, lease: dict[str, Any], model: str | None, workspace: str | None) -> dict[str, Any]:
    ...

def build_new_launch_config(*, provider_config: str, recipe: dict[str, Any] | None, model: str | None, workspace: str | None) -> dict[str, Any]:
    ...
```

- [ ] **Step 2: Deduplicate the two save functions behind one tiny internal helper**

```python
def _save_launch_config(...):
    ...
```

- [ ] **Step 3: Replace router hand-built `successful_config` dicts with service helper calls**

```python
successful_config = build_existing_launch_config(...)
successful_config = build_new_launch_config(...)
```

- [ ] **Step 4: Run focused tests to verify green**

Run: `uv run pytest tests/Fix/test_thread_launch_config_contract.py -q`
Expected: PASS

- [ ] **Step 5: Commit the service/router alignment**

```bash
git add backend/web/services/thread_launch_config_service.py backend/web/routers/threads.py tests/Fix/test_thread_launch_config_contract.py
git commit -m "fix: align thread launch config contract"
```

### Task 3: Final verification and PR prep

**Files:**
- Modify: `docs/superpowers/specs/2026-04-06-thread-launch-config-contract-design.md`
- Modify: `docs/superpowers/plans/2026-04-06-thread-launch-config-contract-alignment.md`

- [ ] **Step 1: Run branch proof**

Run: `uv run pytest tests/Fix/test_thread_launch_config_contract.py tests/Integration/test_threads_router.py -q`
Expected: PASS

Run: `python3 -m py_compile backend/web/services/thread_launch_config_service.py backend/web/routers/threads.py tests/Fix/test_thread_launch_config_contract.py`
Expected: exit 0

Run: `cd frontend/app && npm run build`
Expected: PASS

- [ ] **Step 2: Update docs if implementation exposed any narrower stopline**

Keep the stopline explicit:

- launch-config contract only
- no thread-create policy rewrite
- no monitor/resource spillover

- [ ] **Step 3: Commit docs and verification-ready state**

```bash
git add docs/superpowers/specs/2026-04-06-thread-launch-config-contract-design.md docs/superpowers/plans/2026-04-06-thread-launch-config-contract-alignment.md
git commit -m "docs: capture thread launch config seam"
```
