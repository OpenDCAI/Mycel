# Resource / Monitor Contract Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user-scoped backend resources contract beside the existing global monitor overview, without changing monitor semantics or reviving the old frontend route.

**Architecture:** Keep `resource_cache.py` and `/api/monitor/resources` as the global snapshot path. Introduce a small user projection service plus `GET /api/resources/overview`, sourcing ownership from `sandbox_service.list_user_leases(...)` and reusing only the honest provider/session shaping helpers from `resource_service.py`.

**Tech Stack:** FastAPI, asyncio `to_thread`, Supabase-backed repos, pytest

---

### Task 1: Write focused regression tests for the contract split

**Files:**
- Create: `tests/Fix/test_resource_overview_contract_split.py`
- Read: `backend/web/routers/monitor.py`
- Read: `backend/web/routers/sandbox.py`
- Read: `backend/web/services/resource_service.py`
- Read: `backend/web/services/sandbox_service.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.routers import monitor as monitor_router
from backend.web.routers import resources as resources_router


def test_monitor_resources_stays_global(monkeypatch):
    monkeypatch.setattr(
        monitor_router,
        "get_resource_overview_snapshot",
        lambda: {"summary": {"snapshot_at": "now"}, "providers": [{"id": "global-daytona"}]},
    )

    app = FastAPI()
    app.include_router(monitor_router.router)
    app.dependency_overrides[monitor_router.get_current_user_id] = lambda: "user-1"

    client = TestClient(app)
    response = client.get("/api/monitor/resources")

    assert response.status_code == 200
    assert response.json()["providers"][0]["id"] == "global-daytona"


def test_resources_overview_is_user_scoped(monkeypatch):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        resources_router.resource_projection_service,
        "list_user_resource_providers",
        lambda app, owner_user_id: seen.setdefault("call", (app, owner_user_id)) or {"summary": {}, "providers": []},
    )

    app = FastAPI()
    app.state.thread_repo = object()
    app.state.member_repo = object()
    app.include_router(resources_router.router)
    app.dependency_overrides[resources_router.get_current_user_id] = lambda: "user-7"

    client = TestClient(app)
    response = client.get("/api/resources/overview")

    assert response.status_code == 200
    assert seen["call"][1] == "user-7"


def test_resources_overview_fails_loud_without_required_repos(monkeypatch):
    monkeypatch.setattr(
        resources_router.resource_projection_service,
        "list_user_resource_providers",
        lambda app, owner_user_id: (_ for _ in ()).throw(RuntimeError("thread_repo and member_repo are required")),
    )

    app = FastAPI()
    app.include_router(resources_router.router)
    app.dependency_overrides[resources_router.get_current_user_id] = lambda: "user-7"

    client = TestClient(app)
    response = client.get("/api/resources/overview")

    assert response.status_code == 500
    assert "thread_repo and member_repo are required" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/Fix/test_resource_overview_contract_split.py -q`
Expected: FAIL because `/api/resources/overview` and its router/service do not exist yet.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/Fix/test_resource_overview_contract_split.py
git commit -m "test: cover resource contract split"
```

### Task 2: Introduce the user-scoped resources router and service

**Files:**
- Create: `backend/web/routers/resources.py`
- Create: `backend/web/services/resource_projection_service.py`
- Modify: `backend/web/main.py`

- [ ] **Step 1: Add the new router**

```python
import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.web.core.dependencies import get_current_user_id
from backend.web.services import resource_projection_service

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("/overview")
async def resources_overview(
    user_id: Annotated[str, Depends(get_current_user_id)],
    request: Request,
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            resource_projection_service.list_user_resource_providers,
            request.app,
            user_id,
        )
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
```

- [ ] **Step 2: Add the first minimal projection service**

```python
from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service


def list_user_resource_providers(app: Any, owner_user_id: str) -> dict[str, Any]:
    thread_repo = getattr(app.state, "thread_repo", None)
    member_repo = getattr(app.state, "member_repo", None)
    if thread_repo is None or member_repo is None:
        raise RuntimeError("thread_repo and member_repo are required")

    leases = sandbox_service.list_user_leases(
        owner_user_id,
        thread_repo=thread_repo,
        member_repo=member_repo,
    )
    return {"summary": {"scope": "user", "lease_count": len(leases)}, "providers": []}
```

This first pass is intentionally minimal: create the new bounded surface before pulling shaping logic across.

- [ ] **Step 3: Wire the router into the app**

```python
from backend.web.routers import resources

app.include_router(resources.router)
```

- [ ] **Step 4: Run tests to verify the new route exists**

Run: `uv run pytest tests/Fix/test_resource_overview_contract_split.py -q`
Expected: PASS for the route existence / owner-forwarding tests, with shaping still minimal.

- [ ] **Step 5: Commit the new bounded surface**

```bash
git add backend/web/routers/resources.py backend/web/services/resource_projection_service.py backend/web/main.py tests/Fix/test_resource_overview_contract_split.py
git commit -m "feat: add user-scoped resource overview route"
```

### Task 3: Extract honest shared shaping helpers from resource_service

**Files:**
- Modify: `backend/web/services/resource_service.py`
- Modify: `backend/web/services/resource_projection_service.py`
- Test: `tests/Fix/test_resource_overview_contract_split.py`

- [ ] **Step 1: Pull only reusable shaping helpers behind explicit functions**

Create or expose helpers in `resource_service.py` for things that are not monitor-cache-specific:

```python
def build_provider_catalog_entry(config_name: str) -> dict[str, Any]:
    ...


def build_provider_capabilities(config_name: str) -> tuple[dict[str, bool], str | None]:
    ...


def to_resource_session_payload(session: dict[str, Any], owner: dict[str, Any], metrics: dict[str, Any] | None) -> dict[str, Any]:
    ...
```

Do **not** move:

- `refresh_resource_overview_sync`
- `get_resource_overview_snapshot`
- `_snapshot_drifted_from_live_sessions`

- [ ] **Step 2: Make the user projection shape real provider cards**

Update `resource_projection_service.py` so it:

- groups owner-visible leases by provider config name
- builds provider cards using extracted catalog/capability helpers
- emits session rows shaped like the existing `ProviderInfo` / `ResourceSession` contract
- uses simple user-scoped counts in `summary`

Minimal target shape:

```python
return {
    "summary": {
        "snapshot_at": "...",
        "total_providers": len(providers),
        "active_providers": ...,
        "unavailable_providers": ...,
        "running_sessions": ...,
    },
    "providers": providers,
}
```

- [ ] **Step 3: Expand the focused tests to assert user-facing shape**

Add assertions like:

```python
assert payload["summary"]["total_providers"] == 1
assert payload["providers"][0]["id"] == "daytona_selfhost"
assert payload["providers"][0]["sessions"][0]["leaseId"] == "lease-1"
assert payload["providers"][0]["sessions"][0]["memberName"] == "Morel"
```

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/Fix/test_resource_overview_contract_split.py -q`
Expected: PASS

Run: `uv run pyright backend/web/services/resource_service.py backend/web/services/resource_projection_service.py backend/web/routers/resources.py tests/Fix/test_resource_overview_contract_split.py`
Expected: `0 errors`

- [ ] **Step 5: Commit the shaping extraction**

```bash
git add backend/web/services/resource_service.py backend/web/services/resource_projection_service.py tests/Fix/test_resource_overview_contract_split.py
git commit -m "refactor: split user resource projection from monitor shaping"
```

### Task 4: Prove monitor path is unchanged and cache remains monitor-only

**Files:**
- Modify: `tests/Fix/test_resource_overview_contract_split.py`
- Read: `backend/web/services/resource_cache.py`
- Read: `backend/web/routers/monitor.py`

- [ ] **Step 1: Add an explicit non-regression test for the monitor path**

Add one focused assertion that `/api/monitor/resources` still uses the monitor snapshot path rather than the new user projection service.

```python
def test_monitor_resources_does_not_call_user_projection(...):
    ...
```

- [ ] **Step 2: Keep cache invalidation scope honest**

Verify by test or monkeypatch assertion that:

- thread/message paths still only call `clear_resource_overview_cache()`
- no new user-specific cache is introduced in this slice

- [ ] **Step 3: Run focused verification**

Run: `uv run pytest tests/Fix/test_resource_overview_contract_split.py -q`
Expected: PASS

Run: `python3 -m py_compile backend/web/routers/resources.py backend/web/services/resource_projection_service.py backend/web/services/resource_service.py backend/web/services/resource_cache.py`
Expected: exit 0

- [ ] **Step 4: Commit the monitor non-regression proof**

```bash
git add tests/Fix/test_resource_overview_contract_split.py
git commit -m "test: pin monitor and user resource contract split"
```

### Task 5: Final verification and docs sync

**Files:**
- Modify: `docs/superpowers/specs/2026-04-07-resource-monitor-contract-split-design.md`
- Modify: `docs/superpowers/plans/2026-04-07-resource-monitor-contract-split.md`

- [ ] **Step 1: Run the full seam proof**

Run: `uv run pytest tests/Fix/test_resource_overview_contract_split.py -q`
Expected: PASS

Run: `uv run pyright backend/web/services/resource_service.py backend/web/services/resource_projection_service.py backend/web/routers/resources.py backend/web/routers/monitor.py tests/Fix/test_resource_overview_contract_split.py`
Expected: `0 errors`

Run: `uv run ruff check backend/web/services/resource_service.py backend/web/services/resource_projection_service.py backend/web/routers/resources.py backend/web/routers/monitor.py tests/Fix/test_resource_overview_contract_split.py && uv run ruff format --check backend/web/services/resource_service.py backend/web/services/resource_projection_service.py backend/web/routers/resources.py backend/web/routers/monitor.py tests/Fix/test_resource_overview_contract_split.py`
Expected: PASS

- [ ] **Step 2: Update docs if the exact helper names or stopline changed during implementation**

Keep these facts explicit:

- monitor remains global
- user resources are a separate backend contract
- frontend `/resources` is still not revived in this slice

- [ ] **Step 3: Commit docs and verification-ready state**

```bash
git add docs/superpowers/specs/2026-04-07-resource-monitor-contract-split-design.md docs/superpowers/plans/2026-04-07-resource-monitor-contract-split.md
git commit -m "docs: capture resource monitor contract split"
```
