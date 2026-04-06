# Storage Repo Abstraction Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse repo construction to one composition root so web/runtime code no longer splits between `StorageContainer`, manual lifespan wiring, and `storage_factory.py`.

**Architecture:** Extend `storage/contracts.py` and `storage/container.py` to cover the missing repos, move web startup onto container-backed repo construction, then migrate remaining factory-based callers one seam at a time until `backend/web/core/storage_factory.py` can be deleted. Keep the tree Supabase-only and preserve public app-state repo names.

**Tech Stack:** Python, FastAPI lifespan wiring, Supabase repo implementations, pytest, pyright, ruff

---

### Task 1: Lock the composition-root target with failing tests

**Files:**
- Modify: `tests/Fix/test_storage_repo_abstraction_unification.py`
- Read: `storage/contracts.py`
- Read: `storage/container.py`
- Read: `backend/web/core/lifespan.py`

- [ ] **Step 1: Write a failing container-coverage test**

Add a focused test that asserts `StorageContainer` exposes builders for the missing repos needed by current bypass callers:

```python
def test_storage_container_exposes_bypass_repo_builders():
    container = StorageContainer(supabase_client=_FakeSupabaseClient())

    assert callable(container.panel_task_repo)
    assert callable(container.cron_job_repo)
    assert callable(container.agent_registry_repo)
    assert callable(container.tool_task_repo)
    assert callable(container.sync_file_repo)
```

- [ ] **Step 2: Write a failing lifespan-wiring test**

Add a focused test that asserts `lifespan` reads repo instances from `StorageContainer` rather than directly constructing provider classes:

```python
@pytest.mark.asyncio
async def test_lifespan_wires_member_and_thread_repos_from_storage_container(monkeypatch):
    container = _FakeContainer()
    monkeypatch.setattr("backend.web.core.lifespan.StorageContainer", lambda **_: container)

    async with lifespan(app):
        assert app.state.member_repo is container.member_repo_value
        assert app.state.thread_repo is container.thread_repo_value
```

- [ ] **Step 3: Run the focused red tests**

Run:

```bash
uv run pytest tests/Fix/test_storage_repo_abstraction_unification.py -k 'container_exposes_bypass_repo_builders or lifespan_wires_member_and_thread_repos_from_storage_container' -q
```

Expected: FAIL because container coverage is incomplete and lifespan still manually constructs repos.

### Task 2: Extend contracts and container coverage

**Files:**
- Modify: `storage/contracts.py`
- Modify: `storage/container.py`
- Test: `tests/Fix/test_storage_repo_abstraction_unification.py`

- [ ] **Step 1: Add the missing repo protocols**

Extend `storage/contracts.py` with Protocol definitions for:

- `PanelTaskRepo`
- `CronJobRepo`
- `AgentRegistryRepo`
- `ToolTaskRepo`
- `SyncFileRepo`
- `SandboxMonitorRepo`
- `ResourceSnapshotRepo`
- `ThreadLaunchPrefRepo`
- `AgentConfigRepo`
- `UserSettingsRepo`

Reuse current method surfaces from the existing provider implementations. Do not invent new methods in this slice.

- [ ] **Step 2: Add container builders for the missing repos**

Extend `_REPO_REGISTRY` and `StorageContainer` methods in `storage/container.py` so the container can construct the missing Supabase repos and the resource snapshot adapter.

Keep the container Supabase-only.

- [ ] **Step 3: Run the focused tests to turn them green**

Run:

```bash
uv run pytest tests/Fix/test_storage_repo_abstraction_unification.py -k 'container_exposes_bypass_repo_builders' -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add storage/contracts.py storage/container.py tests/Fix/test_storage_repo_abstraction_unification.py
git commit -m "refactor: extend storage container repo coverage"
```

### Task 3: Move lifespan onto the container-backed repos

**Files:**
- Modify: `backend/web/core/lifespan.py`
- Test: `tests/Fix/test_storage_repo_abstraction_unification.py`

- [ ] **Step 1: Replace manual repo construction with container lookups**

Update `lifespan.py` so it builds one `StorageContainer` and assigns app-state repos from container methods rather than direct provider classes.

Keep the existing app-state names unchanged:

- `member_repo`
- `thread_repo`
- `thread_launch_pref_repo`
- `recipe_repo`
- `chat_repo`
- `invite_code_repo`
- `user_settings_repo`
- `agent_config_repo`
- `contact_repo`

- [ ] **Step 2: Run the focused lifespan test**

Run:

```bash
uv run pytest tests/Fix/test_storage_repo_abstraction_unification.py -k 'lifespan_wires_member_and_thread_repos_from_storage_container' -q
```

Expected: PASS

- [ ] **Step 3: Run touched static checks**

Run:

```bash
uv run pyright backend/web/core/lifespan.py storage/contracts.py storage/container.py tests/Fix/test_storage_repo_abstraction_unification.py
uv run ruff check backend/web/core/lifespan.py storage/contracts.py storage/container.py tests/Fix/test_storage_repo_abstraction_unification.py
uv run ruff format --check backend/web/core/lifespan.py storage/contracts.py storage/container.py tests/Fix/test_storage_repo_abstraction_unification.py
```

Expected: all green

- [ ] **Step 4: Commit**

```bash
git add backend/web/core/lifespan.py tests/Fix/test_storage_repo_abstraction_unification.py
git commit -m "refactor: wire web repos through storage container"
```

### Task 4: Migrate remaining web service bypass callers

**Files:**
- Modify: `backend/web/services/task_service.py`
- Modify: `backend/web/services/cron_job_service.py`
- Modify: `backend/web/services/monitor_service.py`
- Modify: `backend/web/services/resource_service.py`
- Modify: relevant router/background-task callers
- Test: `tests/Fix/test_panel_task_owner_contract.py`
- Test: `tests/Fix/test_resource_overview_contract_split.py`
- Test: `tests/Fix/test_storage_repo_abstraction_unification.py`

- [ ] **Step 1: Change services to accept repo parameters**

Refactor the remaining services so they consume explicit repo arguments and stop calling `storage_factory.py` internally.

- [ ] **Step 2: Update request/background callers to pass repos**

Routes should pass repos from `request.app.state`; background tasks should pass repos from the already-built app container/runtime wiring.

- [ ] **Step 3: Run focused regression tests**

Run:

```bash
uv run pytest tests/Fix/test_panel_task_owner_contract.py tests/Fix/test_resource_overview_contract_split.py tests/Fix/test_storage_repo_abstraction_unification.py -q
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/web/services/task_service.py backend/web/services/cron_job_service.py backend/web/services/monitor_service.py backend/web/services/resource_service.py tests/Fix/test_panel_task_owner_contract.py tests/Fix/test_resource_overview_contract_split.py tests/Fix/test_storage_repo_abstraction_unification.py
git commit -m "refactor: remove web service storage factory bypasses"
```

### Task 5: Migrate runtime callers and delete `storage_factory.py`

**Files:**
- Modify: `core/tools/task/service.py`
- Modify: `core/agents/registry.py`
- Modify: `sandbox/sync/state.py`
- Modify: `sandbox/resource_snapshot.py`
- Modify: `storage/runtime.py`
- Delete: `backend/web/core/storage_factory.py`
- Test: `tests/Integration/test_leon_agent.py`
- Test: `tests/Fix/test_storage_repo_abstraction_unification.py`

- [ ] **Step 1: Remove runtime imports of web-layer storage factory**

Make runtime callers accept injected repos or resolve them through `storage.runtime` / `StorageContainer`.

- [ ] **Step 2: Delete `storage_factory.py`**

Remove the temporary factory only after all callers are migrated.

- [ ] **Step 3: Run focused runtime proofs**

Run:

```bash
uv run pytest tests/Fix/test_storage_repo_abstraction_unification.py tests/Integration/test_leon_agent.py -k 'deferred or storage_repo_abstraction' -q
```

Expected: PASS

- [ ] **Step 4: Run touched static checks**

Run:

```bash
uv run pyright core/tools/task/service.py core/agents/registry.py sandbox/sync/state.py sandbox/resource_snapshot.py storage/runtime.py tests/Fix/test_storage_repo_abstraction_unification.py
uv run ruff check core/tools/task/service.py core/agents/registry.py sandbox/sync/state.py sandbox/resource_snapshot.py storage/runtime.py tests/Fix/test_storage_repo_abstraction_unification.py
uv run ruff format --check core/tools/task/service.py core/agents/registry.py sandbox/sync/state.py sandbox/resource_snapshot.py storage/runtime.py tests/Fix/test_storage_repo_abstraction_unification.py
```

Expected: all green

- [ ] **Step 5: Commit**

```bash
git add core/tools/task/service.py core/agents/registry.py sandbox/sync/state.py sandbox/resource_snapshot.py storage/runtime.py backend/web/core/storage_factory.py tests/Fix/test_storage_repo_abstraction_unification.py
git commit -m "refactor: unify storage repo composition root"
```
