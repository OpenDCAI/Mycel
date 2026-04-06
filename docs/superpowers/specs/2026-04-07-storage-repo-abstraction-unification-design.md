# Storage Repo Abstraction Unification Design

**Date:** 2026-04-07  
**Branch:** `dev`

## Goal

Remove the remaining split repo wiring so storage-backed code stops bouncing between:

- `storage.container.StorageContainer`
- `backend/web/core/lifespan.py` manual repo construction
- `backend/web/core/storage_factory.py` direct helper factories

The outcome should be one honest composition root for repo construction, with callers receiving concrete repos by injection rather than importing provider-specific factories from web code.

## Current Facts

### 1. `StorageContainer` is already Supabase-only

Current [storage/container.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/storage/container.py) is not a `sqlite|supabase` strategy container anymore. It is already a Supabase-only composition root for:

- `checkpoint_repo`
- `run_event_repo`
- `file_operation_repo`
- `summary_repo`
- `queue_repo`
- `eval_repo`
- `sandbox_volume_repo`
- `provider_event_repo`
- `lease_repo`
- `terminal_repo`
- `chat_session_repo`

So the old issue framing about “which strategy should the container choose” is stale. The real seam is coverage, not strategy selection.

### 2. Web startup still hand-wires a second repo composition root

Current [backend/web/core/lifespan.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/core/lifespan.py) manually constructs and stores:

- `member_repo`
- `thread_repo`
- `thread_launch_pref_repo`
- `recipe_repo`
- `chat_repo`
- `invite_code_repo`
- `user_settings_repo`
- `agent_config_repo`
- `contact_repo`
- messaging repos

That means even before looking at `storage_factory.py`, the tree already has two parallel repo wiring styles.

### 3. `storage_factory.py` is a third composition path

Current [backend/web/core/storage_factory.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/core/storage_factory.py) still constructs repos for:

- panel tasks
- cron jobs
- sandbox monitor
- agent registry
- tool tasks
- sync files
- resource snapshot helpers

That factory is imported directly by:

- [backend/web/services/task_service.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/services/task_service.py)
- [backend/web/services/cron_job_service.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/services/cron_job_service.py)
- [backend/web/services/monitor_service.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/services/monitor_service.py)
- [backend/web/services/resource_service.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/services/resource_service.py)
- [backend/web/services/sandbox_service.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/services/sandbox_service.py)
- [core/tools/task/service.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/core/tools/task/service.py)
- [core/agents/registry.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/core/agents/registry.py)
- [sandbox/sync/state.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/sandbox/sync/state.py)
- [sandbox/resource_snapshot.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/sandbox/resource_snapshot.py)

So today the repo layer has three different wiring stories, not two.

### 4. Some services already support injection, others do not

There is existing precedent for honest repo injection:

- panel/member/library/thread launch config paths take repos from `request.app.state`
- `member_service` and `library_service` already expose repo parameters
- `sandbox_service.list_user_leases(...)` already accepts `thread_repo` and `member_repo`

But `task_service`, `cron_job_service`, `monitor_service`, `resource_service`, `TaskService`, `AgentRegistry`, and `SyncState` still self-resolve repos.

### 5. The real architectural problem is ownership

The problem is not “how do we instantiate Supabase repos.” That part already exists.

The problem is:

- repo protocols are incomplete
- repo construction is scattered
- web/runtime code reaches into `backend/web/core/storage_factory.py`
- web composition and runtime composition do not share one boundary

## Problem

Right now repo ownership is split across:

1. `StorageContainer`
2. web `lifespan`
3. web-only `storage_factory.py`

This causes:

- unclear source of truth for provider wiring
- easy regression when a new repo is added in only one place
- runtime code in `core/` and `sandbox/` depending on `backend/web/*`
- hidden provider drift between request-time and runtime-time callers

## Approaches

### Approach 1: Keep `storage_factory.py`, just add missing repos there

Pros:

- smallest immediate diff

Cons:

- preserves the third composition path
- keeps `core/` and `sandbox/` coupled to `backend/web`
- does not solve lifecycle ownership

I do not recommend this.

### Approach 2: Extend `StorageContainer` only for the current bypass repos

Pros:

- removes the temporary factory
- gets panel/task/cron/monitor/runtime repos onto a shared root

Cons:

- still leaves `lifespan.py` as a second manual repo root for member/thread/chat/settings/config repos
- fixes the issue body literally, but not the composition problem honestly

This is better, but still incomplete.

### Approach 3: Make `StorageContainer` the single repo composition root

Pros:

- one place defines repo construction
- `lifespan` becomes wiring/orchestration only
- runtime consumers stop importing web-layer factories
- closes both the issue body seam and the newer manual-lifespan seam

Cons:

- broader than the original issue text
- needs staged implementation to avoid blast radius

This is the recommended approach.

## Chosen Design

Adopt **Approach 3**: `StorageContainer` becomes the sole repo composition root for all storage-backed repos used by web and runtime code.

### Design Rule 1: `StorageContainer` owns repo construction

Extend [storage/contracts.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/storage/contracts.py) and [storage/container.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/storage/container.py) to cover the remaining repos:

- `PanelTaskRepo`
- `CronJobRepo`
- `AgentRegistryRepo`
- `ToolTaskRepo`
- `SyncFileRepo`
- `SandboxMonitorRepo`
- `ResourceSnapshotRepo`
- `MemberRepo`
- `ThreadRepo`
- `ThreadLaunchPrefRepo`
- `ChatRepo`
- `ContactRepo`
- `InviteCodeRepo`
- `UserSettingsRepo`
- `AgentConfigRepo`

The container stays Supabase-only. No `sqlite|supabase` branch comes back.

### Design Rule 2: `lifespan.py` stops constructing repo classes directly

`lifespan.py` should build one `StorageContainer` and assign app-state repos from that container:

- `app.state.member_repo = container.member_repo()`
- `app.state.thread_repo = container.thread_repo()`
- etc.

This keeps the public `app.state.<name>_repo` surface stable while collapsing repo construction to one root.

### Design Rule 3: Runtime consumers must not import web-layer factories

The following callers should accept injected repos or resolve them via `storage.runtime`, not `backend/web/core/storage_factory.py`:

- `TaskService`
- `AgentRegistry`
- `SyncState`
- `sandbox/resource_snapshot.py`

That means `core/` and `sandbox/` stop depending on `backend/web/core`.

### Design Rule 4: Web services become repo-parameter consumers

The remaining bypass services should follow the existing `member_service` / `library_service` pattern:

- `task_service`
- `cron_job_service`
- `monitor_service`
- `resource_service`

They should take repo parameters explicitly and leave construction to callers.

For request-scoped routes, callers pass repos from `request.app.state`.

For background tasks and runtime helpers, callers pass repos from a `StorageContainer` created in the relevant composition root.

### Design Rule 5: `storage_factory.py` is deleted at the end

`backend/web/core/storage_factory.py` exists only because the composition problem was not solved yet. Once the repo protocols and container coverage are honest, that file should disappear.

## Implementation Shape

### Slice 1: Add missing contracts and container builders

First extend protocols and container methods without changing all callers at once.

This creates the honest target boundary while keeping existing behavior stable.

### Slice 2: Move `lifespan.py` onto the container

Replace manual Supabase repo construction in `lifespan.py` with container-derived repos.

This removes the second composition root.

### Slice 3: Move bypass services/runtime users onto injected repos

Convert the remaining `storage_factory.py` callers one seam at a time:

- panel task / cron
- monitor / resource snapshot
- runtime registries and sync state

This should be done in narrow slices, not one giant PR.

### Slice 4: Delete `storage_factory.py`

Only after all callers are moved.

## Testing Strategy

### Required proofs

- focused tests that prove each migrated service consumes injected repos rather than self-constructing
- `lifespan` proof that app-state repo names still exist after switching to container-backed construction
- runtime proofs for `TaskService`, `AgentRegistry`, and `SyncState` after removing `storage_factory.py`

### Useful regression checks

- panel task/cron auth contract tests
- resource overview contract tests
- deferred tool execution tests that touch `ToolTaskRepo`
- sync-file / resource-snapshot focused tests if present

## Stopline

This work is complete when:

- repo construction has one source of truth
- `backend/web/core/storage_factory.py` is deleted
- `core/` and `sandbox/` stop importing web-layer repo factories
- `lifespan.py` stops manually instantiating repo classes

This work should **not** expand into:

- changing provider/storage policy
- reintroducing sqlite fallbacks
- redesigning repo semantics or table schemas
- unrelated router/service refactors beyond repo ownership
