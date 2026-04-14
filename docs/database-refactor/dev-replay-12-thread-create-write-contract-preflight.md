# Database Refactor Dev Replay 12: Thread Create Write Contract Preflight

## Goal

Define the minimal truthful write-side contract that follows replay-10 target
binding and replay-11 read seam:

```text
conceptual target: thread -> sandbox -> workspace
current persisted bridge: thread.current_workspace_id -> workspace -> sandbox
```

This checkpoint is doc/ruling only. It does not implement runtime/API changes,
frontend changes, storage contract edits, SQL/migrations, live DB writes, or
legacy deletion.

## Linkage

- replay-10 established the target binding direction and explicitly separated
  target runtime location from legacy terminal/lease glue
- replay-11 added a strict read seam:
  `backend/web/services/thread_runtime_binding_service.py`
- current mismatch: reads can now resolve `current_workspace_id -> workspace ->
  sandbox`, but thread creation and launch-config persistence still speak in
  legacy lease terms

## Concept Correction

The architectural north star is not `thread -> workspace -> sandbox` as a
product concept.

The product/runtime concept is:

```text
thread -> sandbox
workspace = a thin working directory inside that sandbox
```

However, the currently available persisted pointer on `agent.threads` is
`current_workspace_id`, so the write-side bridge must currently land there.
That does **not** promote workspace into the primary runtime identity. It is
only the concrete persisted anchor we have today.

## Sources

- [dev-replay-10-thread-workspace-sandbox-binding-preflight.md](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/docs/database-refactor/dev-replay-10-thread-workspace-sandbox-binding-preflight.md)
- [requests.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/models/requests.py)
- [threads.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/routers/threads.py)
- [thread_launch_config_service.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/backend/web/services/thread_launch_config_service.py)
- [client.ts](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/frontend/app/src/api/client.ts)
- [NewChatPage.tsx](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/frontend/app/src/pages/NewChatPage.tsx)
- [contracts.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/storage/contracts.py)
- [thread_repo.py](/Users/lexicalmathical/worktrees/leonai--pr188-agent-optimize/storage/providers/supabase/thread_repo.py)

## Current Code Facts

### Request and config surfaces are still lease-centric

- `CreateThreadRequest` still exposes `lease_id`
- `SaveThreadLaunchConfigRequest` still exposes `lease_id`
- frontend `createThread()` still sends `lease_id`
- `NewChatPage` still persists default config with `lease_id` when
  `create_mode = "existing"`

This means the user-facing create/config shell still describes "reuse existing
sandbox" as "reuse existing lease".

### Router create path still derives truth from lease reuse

`backend/web/routers/threads.py:_create_owned_thread()` still:

- reads `payload.lease_id`
- resolves owned lease
- creates the thread row before any workspace pointer exists
- reuses or creates lease resources
- saves last successful config in lease semantics

So the current create path still treats lease identity as the decisive runtime
binding source.

### Thread write contract is behind the read contract

`storage/providers/supabase/thread_repo.py` already reads
`current_workspace_id`, but:

- `SupabaseThreadRepo.create(...)` does not accept `current_workspace_id`
- `storage.contracts.ThreadRow` does not structurally own
  `owner_user_id/current_workspace_id/is_main/branch_index`
- `storage.contracts.ThreadRepo.create(...)` has no
  `current_workspace_id` write slot

So replay-11 established a read seam whose persisted write-side contract does
not yet exist.

## Ruling

### 1. The next implementation slice starts at request/router plus thread write contract

The next implementation checkpoint after this preflight should **not** begin by
editing launch-config persistence.

It must begin by defining a truthful write contract in:

- request normalization / router create flow
- `ThreadRepo.create(...)`
- structural thread row contract

Reason:

- launch-config persistence is downstream metadata
- it must follow the authoritative write contract
- it must not define the contract by itself

### 2. Thread write truth must own `current_workspace_id`

The first truthful write-side landing must make thread creation capable of
writing `current_workspace_id`.

That does **not** mean the product concept becomes workspace-primary. It means:

- sandbox remains the conceptual runtime owner
- workspace remains the concrete mutable workdir inside sandbox
- thread row currently reaches that sandbox through its current workspace pointer

Therefore the minimal landing contract is:

- thread create flow resolves or creates the workspace/sandbox binding first
- thread row persists `current_workspace_id`
- later runtime reads use replay-11 binding seam instead of inventing another
  lease-centric shortcut

### 3. `lease_id` is temporarily tolerated only in narrow legacy shells

Explicit verdict:

- `lease_id` is **temporarily tolerated** at the current HTTP create/config shell
  and saved launch-config shell
- `lease_id` is **not** tolerated as the authoritative thread runtime write
  contract
- `lease_id` must not spread into new storage/thread binding seams

Why this limited tolerance is still legal right now:

- the current frontend create/config UI still lets the user pick "existing"
  through lease-shaped data
- replay-12 is only a preflight; it does not yet authorize that UI contract cut

Why this tolerance is narrow:

- it is a legacy entry shell only
- it does not justify keeping `ThreadRepo.create(...)` workspace-blind
- it does not justify future runtime seams depending on lease identity

### 4. Saved launch-config persistence is not the next checkpoint, but it is now a declared residue

Saved launch-config persistence may still store `lease_id` **for now**, but only
as explicit declared residue.

That residue remains legal until the request/router plus thread write contract
lands. After that, launch-config persistence needs its own follow-up checkpoint
to either:

- persist workspace/sandbox-facing selection truth, or
- prove exactly why a remaining `lease_id` field is still legitimate

No vague "transition period" is allowed.

## Proposed First Implementation Checkpoint After Replay-12

`database-refactor-dev-replay-13-thread-create-current-workspace-write-contract`

Target boundary:

- extend structural thread row / repo create contract to own
  `owner_user_id`, `current_workspace_id`, `is_main`, `branch_index`
- make router create path land a truthful workspace pointer
- keep launch-config persistence cleanup out of that slice
- keep frontend UI contract cleanup out of that slice
- keep runtime/monitor/file-channel/schedule work out of that slice

## Stopline

Replay-12 does **not** authorize:

- runtime/API implementation
- frontend product change
- storage provider implementation changes
- SQL/migrations/live DB writes
- file-channel work
- monitor work
- schedule work
- terminal/lease/volume deletion

## Honest Residuals

- create/config UI still talks in lease terms
- saved launch-config persistence still talks in lease terms
- router create flow still creates thread rows before a workspace pointer exists
- thread write contract still lags behind replay-11 read contract

Those residuals are now explicit. They should not be papered over with more
lease-aware helper glue.
