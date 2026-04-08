# Settings Persistence Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the repeated repo-vs-filesystem persistence branching in `backend/web/routers/settings.py` without changing outward route contracts.

**Architecture:** Keep the seam router-local. Add a small storage context/helper layer inside `settings.py` so workspace, models, observation, and sandbox persistence all resolve storage root explicitly in one place. Do not extract a new service and do not touch `/browse`, `/read`, or `/config`.

**Tech Stack:** FastAPI, Pydantic, pytest, repo-backed `user_settings_repo`, local JSON persistence under `~/.leon`.

---

## File Map

- Modify: `backend/web/routers/settings.py`
  - Add router-local storage-context helpers.
  - Replace repeated `repo + user_id + load/save` branching with domain helpers.
- Create: `tests/Integration/test_settings_persistence_contract.py`
  - Minimal route-contract proof for repo-backed reads/writes and filesystem fallback.
- Reference only: `tests/Integration/test_settings_local_path_shell.py`
  - Must remain unchanged; `/browse` and `/read` are out of scope.

### Task 1: Write minimal persistence contract proof

**Files:**
- Create: `tests/Integration/test_settings_persistence_contract.py`
- Reference: `backend/web/routers/settings.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.web.routers import settings as settings_router


class _FakeSettingsRepo:
    def __init__(self) -> None:
        self.rows = {
            "user-1": {
                "default_workspace": "/repo/ws",
                "recent_workspaces": ["/repo/ws"],
                "default_model": "openai:gpt-5.4",
            }
        }
        self.models = {"user-1": {"pool": {"enabled": ["openai:gpt-5.4"], "custom": []}}}

    def get(self, user_id: str):
        return self.rows.get(user_id)

    def get_models_config(self, user_id: str):
        return self.models.get(user_id)

    def set_models_config(self, user_id: str, data):
        self.models[user_id] = data


def _fake_request(repo: _FakeSettingsRepo | None):
    state = SimpleNamespace(user_settings_repo=repo) if repo is not None else SimpleNamespace()
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_get_settings_prefers_repo_backed_workspace_and_models(monkeypatch: pytest.MonkeyPatch):
    repo = _FakeSettingsRepo()
    req = _fake_request(repo)
    monkeypatch.setattr(settings_router, "_try_get_user_id", lambda _req: "user-1")
    monkeypatch.setattr(settings_router, "load_merged_models", lambda: settings_router.ModelsConfig())

    result = pytest.run(asyncio=settings_router.get_settings(req))

    assert result.default_workspace == "/repo/ws"
    assert result.default_model == "openai:gpt-5.4"
    assert result.enabled_models == ["openai:gpt-5.4"]


def test_toggle_model_writes_repo_when_repo_backed(monkeypatch: pytest.MonkeyPatch):
    repo = _FakeSettingsRepo()
    req = _fake_request(repo)

    pytest.run(
        asyncio=settings_router.toggle_model(
            settings_router.ModelToggleRequest(model_id="anthropic:claude-sonnet-4", enabled=True),
            req,
            "user-1",
        )
    )

    assert "anthropic:claude-sonnet-4" in repo.models["user-1"]["pool"]["enabled"]


def test_workspace_fallback_still_writes_preferences_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings_file = tmp_path / "preferences.json"
    monkeypatch.setattr(settings_router, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_router, "_get_settings_repo", lambda _req: None)
    monkeypatch.setattr(settings_router, "_resolve_workspace_path_or_400", lambda *_args, **_kwargs: "/tmp/ws")

    pytest.run(
        asyncio=settings_router.set_default_workspace(
            settings_router.WorkspaceRequest(workspace="~/tmp/ws"),
            SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
            "user-1",
        )
    )

    assert settings_file.exists()
    assert '"default_workspace": "/tmp/ws"' in settings_file.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify at least one fails**

Run:

```bash
cd /Users/lexicalmathical/worktrees/leonai--code-killer-settings-persistence
uv run pytest tests/Integration/test_settings_persistence_contract.py -q
```

Expected:

```text
FAIL
```

- [ ] **Step 3: Commit the failing test scaffold**

```bash
git add tests/Integration/test_settings_persistence_contract.py
git commit -m "test: add settings persistence contract proof"
```

### Task 2: Add router-local storage context helpers

**Files:**
- Modify: `backend/web/routers/settings.py`
- Test: `tests/Integration/test_settings_persistence_contract.py`

- [ ] **Step 1: Add the storage context helper**

Insert near the existing `_get_settings_repo()` helpers:

```python
class _SettingsStorage:
    def __init__(self, repo: Any | None, user_id: str | None) -> None:
        self.repo = repo
        self.user_id = user_id

    @property
    def repo_backed(self) -> bool:
        return self.repo is not None and self.user_id is not None


def _resolve_settings_storage(request: Request) -> "_SettingsStorage":
    repo = _get_settings_repo(request)
    user_id = _try_get_user_id(request) if repo else None
    return _SettingsStorage(repo, user_id)
```

- [ ] **Step 2: Add domain-specific load/save helpers**

Add router-local helpers:

```python
def _load_workspace_settings(storage: _SettingsStorage) -> WorkspaceSettings:
    if storage.repo_backed:
        row = storage.repo.get(storage.user_id)
        if row is not None:
            return WorkspaceSettings(
                default_workspace=row.get("default_workspace"),
                recent_workspaces=row.get("recent_workspaces") or [],
                default_model=row.get("default_model") or "leon:large",
            )
    return load_settings()


def _save_workspace_settings(storage: _SettingsStorage, settings: WorkspaceSettings) -> None:
    if storage.repo_backed:
        if settings.default_workspace is not None:
            storage.repo.set_default_workspace(storage.user_id, settings.default_workspace)
        storage.repo.set_recent_workspaces(storage.user_id, settings.recent_workspaces)
        storage.repo.set_default_model(storage.user_id, settings.default_model)
        return
    save_settings(settings)


def _load_models_data(storage: _SettingsStorage) -> dict[str, Any]:
    return _load_models_for_user(storage.repo, storage.user_id)


def _save_models_data(storage: _SettingsStorage, data: dict[str, Any]) -> None:
    _save_models_for_user(storage.repo, storage.user_id, data)
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
cd /Users/lexicalmathical/worktrees/leonai--code-killer-settings-persistence
uv run pytest tests/Integration/test_settings_persistence_contract.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 4: Commit helper introduction**

```bash
git add backend/web/routers/settings.py tests/Integration/test_settings_persistence_contract.py
git commit -m "refactor: add settings storage context helpers"
```

### Task 3: Refactor workspace and combined settings routes

**Files:**
- Modify: `backend/web/routers/settings.py`
- Test: `tests/Integration/test_settings_persistence_contract.py`

- [ ] **Step 1: Refactor `get_settings()`**

Replace the inline repo/filesystem split with:

```python
storage = _resolve_settings_storage(request)
ws = _load_workspace_settings(storage)
models = load_merged_models()
raw = _load_models_data(storage)
custom_config = raw.get("pool", {}).get("custom_config", {})
```

- [ ] **Step 2: Refactor workspace/default-model routes**

Use the storage helper in:

```python
@router.post("/workspace")
@router.post("/workspace/recent")
@router.post("/default-model")
```

Pattern:

```python
storage = _resolve_settings_storage(req)
settings = _load_workspace_settings(storage)
settings.default_workspace = workspace_str
_remember_recent_workspace(settings, workspace_str)
_save_workspace_settings(storage, settings)
```

For `add_recent_workspace()`, keep current semantics and do not mutate `default_workspace`.

- [ ] **Step 3: Run the targeted tests**

Run:

```bash
cd /Users/lexicalmathical/worktrees/leonai--code-killer-settings-persistence
uv run pytest tests/Integration/test_settings_persistence_contract.py tests/Integration/test_settings_local_path_shell.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 4: Commit route refactor**

```bash
git add backend/web/routers/settings.py tests/Integration/test_settings_persistence_contract.py
git commit -m "refactor: collapse settings workspace persistence branching"
```

### Task 4: Refactor models, observation, and sandbox persistence routes

**Files:**
- Modify: `backend/web/routers/settings.py`
- Test: `tests/Integration/test_settings_persistence_contract.py`

- [ ] **Step 1: Replace repeated model data branching**

Update these routes to use `_resolve_settings_storage()`, `_load_models_data()`, and `_save_models_data()`:

```python
@router.post("/model-mapping")
@router.post("/models/toggle")
@router.post("/models/custom")
@router.delete("/models/custom")
@router.post("/models/custom/config")
@router.post("/providers")
```

Each route should follow the same shape:

```python
storage = _resolve_settings_storage(req)
data = _load_models_data(storage)
# mutate data in-place
_save_models_data(storage, data)
```

- [ ] **Step 2: Replace repeated observation and sandbox branching**

Add matching helpers:

```python
def _load_observation_data(storage: _SettingsStorage) -> dict[str, Any]: ...
def _save_observation_data(storage: _SettingsStorage, data: dict[str, Any]) -> None: ...
def _load_sandbox_configs(storage: _SettingsStorage) -> dict[str, Any]: ...
def _save_sandbox_configs(storage: _SettingsStorage, data: dict[str, Any]) -> None: ...
```

Then update:

```python
@router.get("/observation")
@router.post("/observation")
@router.get("/sandboxes")
@router.post("/sandboxes")
```

Preserve filesystem behavior exactly when repo-backed mode is inactive.

- [ ] **Step 3: Run verification**

Run:

```bash
cd /Users/lexicalmathical/worktrees/leonai--code-killer-settings-persistence
uv run pytest tests/Integration/test_settings_persistence_contract.py tests/Integration/test_settings_local_path_shell.py tests/Integration/test_storage_repo_abstraction_unification.py -q
python3 -m py_compile backend/web/routers/settings.py tests/Integration/test_settings_persistence_contract.py
uv run ruff check backend/web/routers/settings.py tests/Integration/test_settings_persistence_contract.py
```

Expected:

```text
PASS
```

- [ ] **Step 4: Commit the persistence refactor**

```bash
git add backend/web/routers/settings.py tests/Integration/test_settings_persistence_contract.py
git commit -m "refactor: unify settings persistence storage branching"
```

### Task 5: Final review and handoff

**Files:**
- Modify: `backend/web/routers/settings.py`
- Modify: `tests/Integration/test_settings_persistence_contract.py`

- [ ] **Step 1: Sanity-check the stopline**

Confirm none of these changed:

```text
/browse
/read
/config
response payload shapes
user_settings_repo schema
frontend code
```

- [ ] **Step 2: Run final focused verification**

Run:

```bash
cd /Users/lexicalmathical/worktrees/leonai--code-killer-settings-persistence
uv run pytest tests/Integration/test_settings_persistence_contract.py tests/Integration/test_settings_local_path_shell.py tests/Integration/test_storage_repo_abstraction_unification.py -q
python3 -m py_compile backend/web/routers/settings.py tests/Integration/test_settings_persistence_contract.py
uv run ruff check backend/web/routers/settings.py tests/Integration/test_settings_persistence_contract.py
```

Expected:

```text
PASS
```

- [ ] **Step 3: Commit any final cleanup**

```bash
git add backend/web/routers/settings.py tests/Integration/test_settings_persistence_contract.py
git commit -m "test: finalize settings persistence contract coverage"
```

## Self-Review

- Spec coverage: the plan covers the repeated repo/filesystem branching across workspace, models, observation, and sandbox settings, and explicitly excludes browse/read/hot-reload/front-end work.
- Placeholder scan: no `TODO`/`TBD` markers remain; each task includes concrete files, commands, and code shape.
- Type consistency: helper names are consistent across tasks and remain router-local by design.
