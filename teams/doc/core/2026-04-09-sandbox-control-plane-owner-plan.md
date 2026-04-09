# Sandbox Control-Plane Owner Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Narrow the sandbox control-plane so `backend/web/services/sandbox_service.py` stops owning `sandbox.db` details, then continue toward true Supabase-first parity from the real fused core.

**Architecture:** The first honest cut is not “make SandboxManager Supabase-backed” in one jump. It is to remove `sandbox_service` as an owner of sqlite-kernel details and push that ownership back into `SandboxManager`, then continue by isolating the still-fused `manager + chat_session + sandbox.db` contract.

**Tech Stack:** Python, FastAPI service layer, sandbox runtime/control-plane code, pytest

---

### Task 1: Record the First CP03 Slice

**Files:**
- Modify: `teams/tasks/supabase-first-runtime-parity/_index.md`
- Modify: `teams/tasks/supabase-first-runtime-parity/subtask-03-sandbox-control-plane-parity.md`
- Create: `teams/doc/core/2026-04-09-sandbox-control-plane-owner-plan.md`

- [ ] **Step 1: Record that `sandbox_service.py` is no longer the db-path owner**

Note that the first `CP03` slice only moves `sandbox.db` ownership from `sandbox_service.py` down into `SandboxManager`; it does not claim provider parity is done.

- [ ] **Step 2: Save the remaining fused core**

Document that the remaining control-plane core still lives in:

```text
sandbox/manager.py
sandbox/chat_session.py
```

and that `monitor_service.py` is not part of this first slice.

### Task 2: Write the Failing Test for Service-Level Ownership

**Files:**
- Modify: `tests/Unit/sandbox/test_sandbox_user_leases.py`
- Modify: `backend/web/services/sandbox_service.py`

- [ ] **Step 1: Tighten the source-level contract**

Change the existing source assertion test so it requires:

```python
service_source = Path("backend/web/services/sandbox_service.py").read_text(encoding="utf-8")
assert "storage.providers.sqlite.kernel" not in service_source
assert "resolve_role_db_path" not in service_source
```

- [ ] **Step 2: Run the focused test and watch it fail**

Run:

```bash
uv run pytest -q tests/Unit/sandbox/test_sandbox_user_leases.py -k 'sandbox_service_no_longer_imports_storage_factory'
```

Expected:
- fail because `sandbox_service.py` still imports sqlite kernel directly

- [ ] **Step 3: Make the minimal production change**

Update `backend/web/services/sandbox_service.py` so both manager construction sites become:

```python
SandboxManager(provider=p)
```

and remove:

```python
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
SANDBOX_DB_PATH = ...
```

- [ ] **Step 4: Re-run the focused test to verify green**

Run:

```bash
uv run pytest -q tests/Unit/sandbox/test_sandbox_user_leases.py -k 'sandbox_service_no_longer_imports_storage_factory'
```

Expected:
- pass

### Task 3: Run the Narrow Verification Cluster

**Files:**
- No additional file changes required

- [ ] **Step 1: Verify service/user-lease/provider-availability behavior still holds**

Run:

```bash
uv run pytest -q tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py tests/Integration/test_sandbox_router_user_shell.py -k 'sandbox_service or list_user_leases or available_sandbox_types or sandbox_types'
```

Expected:
- selected tests pass

- [ ] **Step 2: Run lint and compile checks**

Run:

```bash
uv run ruff check backend/web/services/sandbox_service.py tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py tests/Integration/test_sandbox_router_user_shell.py
uv run python -m py_compile backend/web/services/sandbox_service.py tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py tests/Integration/test_sandbox_router_user_shell.py
```

Expected:
- `All checks passed!`
- `exit 0`

### Task 4: Narrow the Real Fused Core Before Another Implementation Cut

**Files:**
- Read: `sandbox/manager.py`
- Read: `sandbox/chat_session.py`
- Modify: `teams/tasks/supabase-first-runtime-parity/subtask-03-sandbox-control-plane-parity.md`

- [ ] **Step 1: Record why `sandbox_service.py` was only the outer shell**

Document that the still-fused owner boundary is:

```text
SandboxManager
ChatSessionManager
SQLite chat_session / lease / terminal repos
connect_sqlite / sandbox.db contract
```

- [ ] **Step 2: Declare the next bounded slice**

Nominate one next move only:
- either `sandbox.manager` repo-construction narrowing
- or `sandbox.chat_session` storage-contract narrowing

Do not combine them in the same implementation slice until the evidence says they are inseparable.

### Task 5: Lease State-Machine Contract Ruling

**Files:**
- Read: `sandbox/lease.py`
- Read: `storage/providers/supabase/lease_repo.py`
- Modify: `teams/tasks/supabase-first-runtime-parity/subtask-03-sandbox-control-plane-parity.md`

- [ ] **Step 1: Record the deeper residual**

Document that after repo-construction cleanup, `sandbox/lease.py` still directly owns sqlite state-machine writes through:

```python
_connect(...)
_append_event(...)
_persist_snapshot(...)
_persist_lease_metadata(...)
```

- [ ] **Step 2: Compare against the current Supabase repo**

Record that `SupabaseLeaseRepo` currently covers only the narrower surface:

```python
get(...)
create(...)
adopt_instance(...)
mark_needs_refresh(...)
delete(...)
list_*
```

and does not yet expose a lease snapshot / instance upsert / event append write contract.

- [ ] **Step 3: Set the next stopline**

State explicitly that the next implementation cut, if any, must start by extending the lease repo contract. It must not be framed as another “remove SQLite import” cleanup.

### Task 6: Lease Repo Contract Extension Design

**Files:**
- Read: `storage/contracts.py`
- Read: `storage/providers/sqlite/lease_repo.py`
- Read: `storage/providers/supabase/lease_repo.py`
- Modify: `teams/tasks/supabase-first-runtime-parity/subtask-03-sandbox-control-plane-parity.md`
- Modify: `teams/doc/core/2026-04-09-sandbox-control-plane-owner-plan.md`

- [ ] **Step 1: Record the exact protocol gap**

Document that current `LeaseRepo` covers:

```python
get(...)
create(...)
find_by_instance(...)
adopt_instance(...)
mark_needs_refresh(...)
delete(...)
list_all(...)
list_by_provider(...)
```

but `sandbox/lease.py` still needs a deeper write surface for:

```python
lease snapshot writes
instance upsert / detached-instance updates
lease event append
lease metadata persistence on error paths
```

- [ ] **Step 2: Name the likely seam**

Propose one explicit contract shape only, for example:

```python
persist_snapshot(...)
append_event(...)
persist_metadata(...)
```

or a single higher-level:

```python
apply_transition(...)
```

Do not implement both options. Pick one recommended shape and record why.

Current ruling after the first metadata slice:

```text
completed first cut:
- LeaseRepo.persist_metadata(...)
- SQLiteLease._record_provider_error() now uses strategy lease repo under supabase

remaining next cut:
- prefer one higher-level apply_transition(...)
- do not keep expanding raw sqlite helper methods one by one
```

Latest update after the observe-status slice:

```text
completed second transition cut:
- LeaseRepo.observe_status(...)
- storage.runtime.build_provider_event_repo(...)
- refresh_instance_status() supabase success path now uses strategy repos

remaining wider transitions:
- intent.pause / intent.resume
- intent.destroy
```

Latest update after the provider-error slice:

```text
completed third transition cut:
- _record_provider_error(..., source=...)
- supabase strategy now records provider.error into provider_events

remaining wider transitions:
- intent.pause / intent.resume
```

Latest update after the destroy slice:

```text
completed fourth transition cut:
- intent.destroy now uses strategy repos under supabase
- destroy path keeps lease-level lock + reload before mutation
- destroy failures now reuse provider.error persistence/event parity
- post-destroy strategy write failures still preserve destroy-state truth before error persistence
- destroy error persistence also preserves the next version step after observe-status writes

remaining wider transitions:
- intent.pause / intent.resume
```

Latest update after the pause/resume slice:

```text
completed fifth transition cut:
- intent.pause / intent.resume now use strategy repos under supabase
- pause/resume keep lease-level lock + reload before mutation
- pause/resume failures reuse provider.error persistence/event parity
- post-write failures preserve pause-state truth and version parity

current bounded stopline:
- transition set for CP03 is complete
- next work should move to CP04 / higher-level closure proof
```

- [ ] **Step 3: Record the transaction question**

Make the plan explicit that SQLite currently gets atomicity from one local connection in:

```python
with _connect(self.db_path) as conn:
    ...
```

so any Supabase-side contract extension must answer whether:
- strict single-transaction parity is required
- or best-effort ordered writes are acceptable for this lane

- [ ] **Step 4: Keep the next move bounded**

State that the next code slice, if authorized, should only:
- extend `LeaseRepo` protocol
- extend `SQLiteLeaseRepo` and `SupabaseLeaseRepo`
- switch one narrow `sandbox/lease.py` write path to the new repo contract

and must not try to migrate the entire lease state machine in one PR.
