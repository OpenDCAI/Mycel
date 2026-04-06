# Resource Observability Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate global monitor resources from user-visible product resources while moving the monitor/resource truth chain onto Supabase-backed wiring honestly enough that the system is not pretending local SQLite is still the only source of truth.

**Architecture:** The implementation is split into two reviewable cuts. Cut A handles sandbox truth-source rewiring so lease/terminal/chat-session construction stops hardcoding SQLite-only repo creation. Cut B moves monitor/resource reads onto the shared storage abstraction, keeps `/api/monitor/resources` global, and introduces `/api/resources/*` for the product contract.

**Tech Stack:** Python, FastAPI, Supabase-backed storage providers, existing storage contract/container abstractions, pytest, ruff

**Execution note:** `#209` remains useful transplant material for the resource split, but active continuation moved to `#210` because the correct monitor baseline is the compat monitor from `PR #182`, not the reduced dev monitor shell. The frontend scope here stays bounded: keep the full compat operator surface, switch it to a lighter and clearer ops shell, and prove it with real Playwright traces instead of a component-only pass.

**Additional sequencing note after live operator review:** before this branch is mergeable as a monitor base, the next follow-up cuts must address four honesty seams now visible in the real UI: `D1` threads pagination contract, `D2` provisional evaluation detail as an operator surface, `D3` lease orphan/diverged regrouping, and `D4` dashboard + global resources entry.

**Current execution order after `D1`:**
- `D4` dashboard + global resources entry
- `D3` lease semantics/regrouping inside the new resources surface
- `D2` provisional evaluation operator surface

**Live progress after latest frontend pass:**
- `D1` is done
- `D4` now has a landed phase-1:
  - `/dashboard` route and `/api/monitor/dashboard` backend payload exist
  - top nav is `Dashboard / Threads / Resources / Eval`
  - root lands on `/dashboard`
  - monitor `Resources` uses the global monitor contract and includes grouped lease triage
  - evaluation tutorial/reference sections are collapsed by default
- `D4` now has a landed phase-2:
  - monitor provider cards now expose a product-like status light, metric cells, capability strip, and session dots
  - selected provider detail now reads like a real panel instead of a loose stats stack
  - null telemetry in monitor resources no longer renders as fake `0.0` values
- `D4` now has a landed phase-3:
  - selected provider detail now shows a lease card grid before the raw session table
  - monitor keeps the raw session table for truth, but no longer forces operators to start from the noisiest surface
- `D2` now has a landed phase-2:
  - evaluation detail payload includes backend-owned `info.operator_surface`
  - provisional eval detail opens with `Operator Status`, artifact paths, and explicit next steps
  - redundant provisional score metadata is folded behind `Score artifacts (provisional)` instead of occupying the first screen
  - operator payload now includes typed lifecycle `kind` and `artifact_summary`
  - all six artifact slots stay visible with explicit `present|missing` status instead of silently dropping missing files
- `D3` now has a landed phase-2:
  - `/api/monitor/leases` now adds backend-owned `triage.summary` and `triage.groups`
  - triage distinguishes `active_drift`, `detached_residue`, `orphan_cleanup`, and `healthy_capacity`
  - monitor `Resources` consumes that triage surface directly instead of flattening everything back into `diverged/orphan`
  - legacy `/leases` also now leads with triage buckets before the collapsed raw table
- next honest follow-up remains:
  - `D3` because lease regrouping is still heuristic and needs stronger lifecycle meaning than age-based detached residue alone

---

### Task 1: Lock Storage Abstraction For Monitor Reads

**Files:**
- Modify: `storage/contracts.py`
- Modify: `storage/container.py`
- Modify: `backend/web/core/storage_factory.py`
- Test: `tests/Unit/storage/test_storage_container.py`

- [ ] **Step 1: Write the failing test**

```python
def test_storage_container_builds_sandbox_monitor_repo_with_supabase(fake_supabase_client):
    container = StorageContainer(strategy="supabase", supabase_client=fake_supabase_client)

    repo = container.sandbox_monitor_repo()

    assert repo.__class__.__name__ == "SupabaseSandboxMonitorRepo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/Unit/storage/test_storage_container.py -k sandbox_monitor_repo`
Expected: FAIL because `StorageContainer` has no `sandbox_monitor_repo()` and no `SandboxMonitorRepo` contract.

- [ ] **Step 3: Write minimal implementation**

```python
class SandboxMonitorRepo(Protocol):
    def query_threads(self, *, thread_id: str | None = None) -> list[dict[str, Any]]: ...
    def query_thread_summary(self, thread_id: str) -> dict[str, Any] | None: ...
    def query_thread_sessions(self, thread_id: str) -> list[dict[str, Any]]: ...
    def query_leases(self) -> list[dict[str, Any]]: ...
    def list_leases_with_threads(self) -> list[dict[str, Any]]: ...
    def query_lease(self, lease_id: str) -> dict[str, Any] | None: ...
    def query_lease_threads(self, lease_id: str) -> list[dict[str, Any]]: ...
    def query_lease_events(self, lease_id: str) -> list[dict[str, Any]]: ...
    def query_diverged(self) -> list[dict[str, Any]]: ...
    def query_events(self, limit: int = 100) -> list[dict[str, Any]]: ...
    def query_event(self, event_id: str) -> dict[str, Any] | None: ...
    def count_rows(self, table_names: list[str]) -> dict[str, int]: ...
    def list_sessions_with_leases(self) -> list[dict[str, Any]]: ...
    def list_probe_targets(self) -> list[dict[str, Any]]: ...
    def query_lease_instance_id(self, lease_id: str) -> str | None: ...
    def close(self) -> None: ...
```

```python
_REPO_REGISTRY["sandbox_monitor_repo"] = (
    "storage.providers.supabase.sandbox_monitor_repo",
    "SupabaseSandboxMonitorRepo",
)
```

```python
def sandbox_monitor_repo(self) -> SandboxMonitorRepo:
    return self._build_repo("sandbox_monitor_repo", self._sqlite_sandbox_monitor_repo)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/Unit/storage/test_storage_container.py -k sandbox_monitor_repo`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add storage/contracts.py storage/container.py backend/web/core/storage_factory.py tests/Unit/storage/test_storage_container.py
git commit -m "refactor: move sandbox monitor repo into storage container"
```

### Task 2: Make Sandbox Repo Construction Strategy-Aware

**Files:**
- Modify: `backend/web/core/storage_factory.py`
- Modify: `sandbox/manager.py`
- Modify: `sandbox/chat_session.py`
- Modify: `backend/web/utils/helpers.py`
- Modify: `backend/web/services/file_channel_service.py`
- Modify: `backend/web/services/activity_tracker.py`
- Modify: `backend/web/routers/threads.py`
- Modify: `backend/web/routers/webhooks.py`
- Test: `tests/Unit/backend/web/core/test_storage_factory.py`

- [ ] **Step 1: Write the failing test**

```python
def test_make_lease_repo_uses_supabase_when_strategy_is_supabase(monkeypatch, fake_supabase_client):
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv("LEON_SUPABASE_CLIENT_FACTORY", "tests.support.fake_supabase:create_client")

    repo = make_lease_repo()

    assert repo.__class__.__name__ == "SupabaseLeaseRepo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/Unit/backend/web/core/test_storage_factory.py -k 'make_lease_repo or make_terminal_repo or make_chat_session_repo'`
Expected: FAIL because these factories do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def make_lease_repo(db_path: Any = None) -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.lease_repo import SupabaseLeaseRepo
        return SupabaseLeaseRepo(client=_supabase_client())
    from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
    return SQLiteLeaseRepo(db_path=db_path)
```

```python
def make_terminal_repo(db_path: Any = None) -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.terminal_repo import SupabaseTerminalRepo
        return SupabaseTerminalRepo(client=_supabase_client())
    from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo
    return SQLiteTerminalRepo(db_path=db_path)
```

```python
def make_chat_session_repo(db_path: Any = None) -> Any:
    if _strategy() == "supabase":
        from storage.providers.supabase.chat_session_repo import SupabaseChatSessionRepo
        return SupabaseChatSessionRepo(client=_supabase_client())
    from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
    return SQLiteChatSessionRepo(db_path=db_path)
```

```python
self.terminal_store = make_terminal_repo(db_path=self.db_path)
self.lease_store = make_lease_repo(db_path=self.db_path)
self.session_manager = ChatSessionManager(
    provider=provider,
    db_path=self.db_path,
    default_policy=ChatSessionPolicy(),
    chat_session_repo=make_chat_session_repo(db_path=self.db_path),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/Unit/backend/web/core/test_storage_factory.py -k 'make_lease_repo or make_terminal_repo or make_chat_session_repo'`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/web/core/storage_factory.py sandbox/manager.py sandbox/chat_session.py backend/web/utils/helpers.py backend/web/services/file_channel_service.py backend/web/services/activity_tracker.py backend/web/routers/threads.py backend/web/routers/webhooks.py tests/Unit/backend/web/core/test_storage_factory.py
git commit -m "refactor: route sandbox repo construction through storage strategy"
```

### Task 3: Split Global Monitor Routes From Product Resource Routes

**Files:**
- Create: `backend/web/routers/resources.py`
- Modify: `backend/web/routers/monitor.py`
- Modify: `backend/web/core/lifespan.py`
- Modify: `backend/web/services/monitor_service.py`
- Modify: `backend/web/services/resource_service.py`
- Modify: `backend/web/services/sandbox_service.py`
- Test: `tests/Integration/test_monitor_resources_route.py`
- Test: `tests/Integration/test_resources_route.py`

- [ ] **Step 1: Write the failing test**

```python
def test_resources_overview_route_is_not_served_from_monitor_prefix(client):
    response = client.get("/api/resources/overview")

    assert response.status_code == 200
```

```python
def test_monitor_resources_route_remains_available_for_global_view(client):
    response = client.get("/api/monitor/resources")

    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/Integration/test_resources_route.py tests/Integration/test_monitor_resources_route.py`
Expected: FAIL because `/api/resources/overview` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
router = APIRouter(prefix="/api/resources", tags=["resources"])

@router.get("/overview")
def get_resources_overview(request: Request, current_user=Depends(require_current_user)):
    return list_resource_providers(request.app.state, current_user_id=current_user.user_id)
```

```python
monitor_repo = request.app.state.storage_container.sandbox_monitor_repo()
```

```python
app.include_router(resources_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/Integration/test_resources_route.py tests/Integration/test_monitor_resources_route.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/web/routers/resources.py backend/web/routers/monitor.py backend/web/core/lifespan.py backend/web/services/monitor_service.py backend/web/services/resource_service.py backend/web/services/sandbox_service.py tests/Integration/test_resources_route.py tests/Integration/test_monitor_resources_route.py
git commit -m "feat: split global monitor resources from product resources api"
```

### Task 4: Rewire Frontend Resource Consumer Minimally

**Files:**
- Modify: `frontend/app/src/pages/resources/api.ts`
- Modify: `frontend/app/src/pages/ResourcesPage.tsx`
- Modify: `frontend/app/src/pages/resources/ProviderCard.tsx`
- Test: `frontend/app/src/pages/resources/api.test.ts`
- Test: Playwright CLI product trace on `/resources`

- [ ] **Step 1: Write the failing test**

```ts
it("fetches overview from /api/resources/overview", async () => {
  await fetchResourcesOverview();
  expect(fetch).toHaveBeenCalledWith("/api/resources/overview", expect.anything());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/app && npm test -- api.test.ts`
Expected: FAIL because the client still calls `/api/monitor/resources`.

- [ ] **Step 3: Write minimal implementation**

```ts
export async function fetchResourcesOverview() {
  return requestJson("/api/resources/overview");
}
```

```tsx
<div data-testid="resources-page" className="h-full flex flex-col bg-background">
```

```tsx
<h2 data-testid="resources-header" className="text-sm font-semibold text-foreground">资源</h2>
```

```tsx
<span data-testid="active-count" className="inline-flex items-center gap-1">...</span>
```

```tsx
<span data-testid="session-count">{totalSessions} 会话</span>
```

```tsx
<button data-testid="refresh-btn" type="button" ...>
```

```tsx
<button data-testid="provider-card" data-provider-id={provider.id} ...>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/app && npm test -- api.test.ts`
Expected: PASS

Run: `npx playwright test <product-resources-spec>`
Expected: `/resources` renders, provider cards are visible, and real network traces show `/api/resources/overview` with no `/api/monitor/resources`

- [ ] **Step 5: Commit**

```bash
git add frontend/app/src/pages/resources/api.ts frontend/app/src/pages/ResourcesPage.tsx frontend/app/src/pages/resources/ProviderCard.tsx frontend/app/src/pages/resources/api.test.ts
git commit -m "feat: point resources page at user-scoped resources api"
```

### Task 5: Prove The Claim Boundary Honestly

**Files:**
- Modify: `docs/superpowers/specs/2026-04-06-resource-observability-split-design.md`
- Modify: `README.md`
- Test: `tests/Integration/test_monitor_resources_route.py`
- Test: Playwright CLI probe against product resources route
- Test: Playwright CLI probe against global monitor resources route

- [ ] **Step 1: Write the failing test**

```python
def test_monitor_health_reports_strategy_specific_backend_shape(client):
    payload = client.get("/api/monitor/health").json()
    assert "strategy" in payload["db"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/Integration/test_monitor_resources_route.py -k health`
Expected: FAIL if health still assumes only local SQLite file diagnostics.

- [ ] **Step 3: Write minimal implementation**

```python
if storage_strategy == "supabase":
    db = {"strategy": "supabase", "reachable": reachable}
else:
    db = {"strategy": "sqlite", "path": str(db_path), "exists": db_exists}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/Integration/test_monitor_resources_route.py -k health`
Expected: PASS

- [ ] **Step 5: Run Playwright CLI verification**

Run: `npx playwright test <product-resources-spec>`
Expected: product resources UI loads from `/resources`, uses the user-scoped route, and does not rely on `/api/monitor/resources`

Run: `npx playwright test <monitor-resources-spec>`
Expected: monitor `/leases` UI still loads from the global monitor contract and never falls through to `/api/resources/*`

- [ ] **Step 6: Commit**

```bash
git add backend/web/services/monitor_service.py tests/Integration/test_monitor_resources_route.py docs/superpowers/specs/2026-04-06-resource-observability-split-design.md README.md
git commit -m "docs: record observability split proof boundary"
```
