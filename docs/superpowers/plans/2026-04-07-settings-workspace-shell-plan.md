# Settings Workspace Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate the settings router's workspace normalization and recent-list update shell while preserving the different contracts of `set_default_workspace` and `add_recent_workspace`.

**Architecture:** Keep the change inside `backend/web/routers/settings.py`. Introduce one helper for path normalization/validation with route-provided error strings, plus one helper for recent-list mutation. Keep repo/local persistence and `default_workspace` ownership inside the routes.

**Tech Stack:** FastAPI, pytest, Python 3.12

---

### Task 1: Lock The Router Shell With Failing Tests

**Files:**
- Create: `tests/Integration/test_settings_workspace_router.py`
- Reference: `backend/web/routers/settings.py`

- [ ] **Step 1: Add focused tests for the helpers and route delegation**

Add tests that cover:

```python
def test_resolve_workspace_path_or_400_returns_normalized_path(tmp_path: Path) -> None:
    ...


def test_resolve_workspace_path_or_400_uses_route_specific_messages(tmp_path: Path) -> None:
    ...


def test_remember_recent_workspace_dedupes_and_truncates() -> None:
    ...


@pytest.mark.asyncio
async def test_set_default_workspace_uses_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    ...


@pytest.mark.asyncio
async def test_add_recent_workspace_uses_helpers_without_changing_default(monkeypatch: pytest.MonkeyPatch) -> None:
    ...
```

- [ ] **Step 2: Run the focused settings workspace router test file and verify RED**

Run: `uv run pytest tests/Integration/test_settings_workspace_router.py -q`

Expected: FAIL because the new helper contracts do not exist yet.

### Task 2: Implement The Minimal Router-Local Helpers

**Files:**
- Modify: `backend/web/routers/settings.py`
- Test: `tests/Integration/test_settings_workspace_router.py`

- [ ] **Step 1: Add the minimal helpers**

Add:

```python
def _resolve_workspace_path_or_400(... ) -> str:
    ...


def _remember_recent_workspace(settings: WorkspaceSettings, workspace_str: str) -> None:
    ...
```

- [ ] **Step 2: Replace only the duplicated shell**

Update only:

```python
set_default_workspace(...)
add_recent_workspace(...)
```

Keep:

- route-specific validation messages
- `set_default_workspace` mutating `default_workspace`
- `add_recent_workspace` not mutating `default_workspace`
- repo/local persistence branching

- [ ] **Step 3: Run the focused settings workspace router test file and verify GREEN**

Run: `uv run pytest tests/Integration/test_settings_workspace_router.py -q`

Expected: PASS

### Task 3: Run Regression Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the focused regression set**

Run: `uv run pytest tests/Integration/test_settings_workspace_router.py tests/Integration/test_invite_codes_router.py tests/Integration/test_messaging_router.py -q`

Expected: PASS

- [ ] **Step 2: Run syntax verification**

Run: `python3 -m py_compile backend/web/routers/settings.py tests/Integration/test_settings_workspace_router.py`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/web/routers/settings.py tests/Integration/test_settings_workspace_router.py docs/superpowers/specs/2026-04-07-settings-workspace-shell-design.md docs/superpowers/plans/2026-04-07-settings-workspace-shell-plan.md
git commit -m "fix: align settings workspace shell"
```
