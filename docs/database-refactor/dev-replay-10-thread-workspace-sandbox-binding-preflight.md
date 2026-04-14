# Database Refactor Dev Replay 10: Thread Workspace Sandbox Binding Preflight

## Goal

Define the target contract that replaces the current runtime glue:

```text
thread -> terminal -> lease -> instance / volume
```

with target database design:

```text
thread -> current_workspace_id -> container.workspaces -> container.sandboxes -> container.devices / provider_env_id
```

This checkpoint is doc-only. It does not implement the resolver, edit storage
contracts, add migrations, write live DB data, delete legacy tables, change
runtime/API behavior, touch frontend, or resume schedule work.

## Sources

Target design:

- `/Users/lexicalmathical/Codebase/mycel-db-design`
- design commit `9422bd8b1f76f323605ad34240d57eecbddf5439`
- `agent-schema.md`
- `container-schema.md`
- `schema-decisions.md`
- `overview.md`
- GitHub issue `nmhjklnm/mycel-db-design#1`

Current Mycel code:

- `storage/providers/supabase/thread_repo.py`
- `storage/contracts.py`
- `backend/web/routers/threads.py`
- `backend/web/services/thread_launch_config_service.py`
- `backend/web/services/sandbox_service.py`
- `backend/web/services/file_channel_service.py`
- `backend/web/services/thread_runtime_convergence.py`
- `backend/web/services/thread_state_service.py`
- `backend/web/services/resource_projection_service.py`
- `sandbox/manager.py`
- `sandbox/capability.py`
- `sandbox/chat_session.py`
- `sandbox/sync/state.py`
- `sandbox/sync/strategy.py`

## Target Contract Facts

### Agent thread owns the workspace pointer

Target `agent.threads` includes:

- `current_workspace_id TEXT`
- app-layer relation to `container.workspaces.id`
- nullable, because target design allows an agent thread to run without a
  workspace
- updateable by owner for workspace switching
- indexed by `idx_threads_workspace`

The target design explicitly says thread/workspace is a switchable connection,
not a 1:1 binding.

### Container hierarchy owns runtime location

Target `container` hierarchy is:

```text
container.devices
  -> container.sandboxes
      -> container.workspaces
```

Relevant fields:

- `container.sandboxes.device_id`
- `container.sandboxes.provider_name`
- `container.sandboxes.provider_env_id`
- `container.sandboxes.template_id`
- `container.sandboxes.config`
- `container.sandboxes.desired_state`
- `container.sandboxes.observed_state`
- `container.workspaces.sandbox_id`
- `container.workspaces.workspace_path`
- `container.workspaces.desired_state`
- `container.workspaces.observed_state`
- `container.workspaces.needs_refresh`

### Terminal is not part of the target binding

Latest design issue resolution deletes:

- terminal entity
- terminal pointer
- terminal command table
- terminal command chunk table

Therefore the replacement binding surface cannot expose `terminal_id` as a
required runtime identity.

## Current Code Facts

### Current thread repo partially knows the target field

`storage/providers/supabase/thread_repo.py` selects `current_workspace_id` in
`_COLS`, so reads can already carry the target pointer when present.

However:

- `SupabaseThreadRepo.create(...)` does not accept or insert
  `current_workspace_id`
- `storage.contracts.ThreadRow` does not contain `owner_user_id`,
  `current_workspace_id`, `is_main`, or `branch_index`
- `backend/web/routers/threads.py` create path still passes only `sandbox_type`,
  `cwd`, `model`, and branch metadata to `thread_repo.create(...)`

This means the target column exists in the read model but is not yet a complete
runtime contract.

### Current launch still creates old runtime glue

`backend/web/routers/threads.py` currently does this for new threads:

```text
create agent thread row
create sandbox volume row
create sandbox lease row with volume_id + recipe snapshot
create terminal row with initial cwd
save last successful launch config
```

For existing runtime reuse, it does this:

```text
resolve owned lease
bind new thread to existing lease by creating/reusing terminal binding
save last successful launch config with lease_id
```

So the current product concept called "existing sandbox" is effectively
"reuse existing lease".

### Current runtime capability is terminal-centered

`sandbox/manager.py` resolves an active thread runtime by:

- loading active/default terminal for thread
- loading lease through terminal.lease_id
- using terminal cwd/env state
- creating `ChatSession`
- using lease instance for provider execution

Important current invariants:

- active thread must have active terminal or terminal rows that can restore a
  pointer
- all terminals for a thread must share one lease
- file sync and volume resolution walk through active terminal
- async/background commands fork a new terminal from the default terminal state

### Current file channel is still volume-centered

`backend/web/services/file_channel_service.py` resolves file channel source by:

```text
thread -> active terminal -> lease -> volume_id -> sandbox_volumes.source
```

The target design deletes volumes and says upload/download should go through
Supabase Storage. This is a later migration. The binding preflight must not
pretend `current_workspace_id` alone already solves file channel behavior.

### Current monitor/read projections are lease-centered

Monitor and resource projection services read:

- `chat_sessions`
- `sandbox_leases`
- `abstract_terminals`
- `provider_events`
- `lease_resource_snapshots`

Target projection should read:

- `container.workspaces`
- `container.sandboxes`
- `container.provider_events`
- `container.resource_snapshots`

The monitor cannot be rewritten safely until the thread/workspace/sandbox
binding is explicit.

## Target Resolver Contract

The replacement surface should be a small read contract, not another large
manager. Its job is to answer one question:

> For this thread, what workspace and sandbox should runtime operations use?

### Proposed input

```python
resolve_thread_runtime_binding(
    *,
    thread_id: str,
    owner_user_id: str | None = None,
    purpose: Literal["run", "file_channel", "monitor", "launch_default"],
)
```

`owner_user_id` is optional for internal runtime calls that already operate on a
trusted thread id. It is required for user-facing surfaces.

`purpose` is intentionally explicit. It prevents one resolver from hiding
different product semantics behind conditionals:

- `run`: agent/tool execution
- `file_channel`: user/agent upload/download surface
- `monitor`: owner-visible runtime projection
- `launch_default`: new-thread default selection and existing workspace reuse

### Proposed output

```python
ThreadRuntimeBinding:
    thread_id: str
    owner_user_id: str
    agent_user_id: str
    workspace_id: str | None
    workspace_path: str | None
    workspace_status: str | None
    workspace_desired_state: str | None
    workspace_observed_state: str | None
    sandbox_id: str | None
    device_id: str | None
    provider_name: str
    provider_env_id: str | None
    sandbox_status: str | None
    sandbox_desired_state: str | None
    sandbox_observed_state: str | None
    sandbox_template_id: str | None
    sandbox_config: dict
    model: str | None
    legacy_cwd: str | None
```

Notably absent:

- `terminal_id`
- `active_terminal_id`
- `default_terminal_id`
- `chat_session_id`
- `lease_id`
- `volume_id`

Legacy ids may appear in temporary migration diagnostics, but they must not be
part of the target contract.

### Failure rules

The resolver should fail loudly when a product path requires a workspace but the
thread has none.

Examples:

- `purpose="run"` may allow `workspace_id=None` only if the runtime has a
  clearly defined no-workspace execution mode.
- `purpose="file_channel"` must not silently fall back to terminal/volume once
  the file-channel migration starts.
- `purpose="monitor"` may return rows with missing workspace only as explicit
  legacy residue, not as healthy runtime state.

## Current To Target Mapping

| Current fact | Target fact | Notes |
|---|---|---|
| `agent.threads.cwd` | `container.workspaces.workspace_path` | `threads.cwd` remains legacy compat. Runtime should prefer workspace path. |
| `agent.threads.sandbox_type` | `container.sandboxes.provider_name` | Current thread stores provider directly; target provider belongs to sandbox. |
| `agent.threads.current_workspace_id` | `container.workspaces.id` | Current Supabase repo reads it but create path does not write it. |
| `sandbox_leases.lease_id` | `container.workspaces.id` or migration-only legacy id | Concrete DDL says workspaces are old lease semantics. Do not map old lease to sandbox just because one older decisions table said so. |
| `sandbox_leases.provider_name` | `container.sandboxes.provider_name` | Provider belongs to sandbox, not workspace. |
| `sandbox_leases.current_instance_id` | `container.sandboxes.provider_env_id` | `sandbox_instances` is absorbed into sandbox provider identity. |
| `sandbox_leases.recipe_id` | `container.sandboxes.template_id` | Existing recipe snapshots become sandbox template/config semantics. |
| `sandbox_leases.recipe_json` | `container.sandboxes.config` | Store effective config, not mutable template reference only. |
| `sandbox_leases.desired_state` | `container.workspaces.desired_state` and/or `container.sandboxes.desired_state` | Split must be explicit; workspace state and sandbox state are distinct. |
| `sandbox_leases.observed_state` | `container.workspaces.observed_state` and/or `container.sandboxes.observed_state` | Split must be explicit; do not collapse daemon sandbox state into workspace state. |
| `abstract_terminals.cwd` | `container.workspaces.workspace_path` plus runtime process cwd | Terminal cwd is currently mutable command state. Target needs a product ruling for per-command cwd persistence. |
| `chat_sessions` | runtime memory / run events / observability | Target says no chat session table. Command/session history needs a separate ruling. |
| `sandbox_volumes.source` | file channel storage contract | Target deletes volumes. The replacement is not part of this binding doc. |
| `sync_files` | sync implementation state or removal | Not a user-facing file index. Replacement must be decided during file-channel/sync checkpoint. |
| `library_recipes` | `container.sandbox_templates` | Rename/migrate concept; do not delete behavior. |
| `lease_resource_snapshots` | `container.resource_snapshots` | Rename/migrate after workspace/sandbox ids exist. |
| `provider_events.matched_lease_id` | `container.provider_events` linked to sandbox/workspace | Target keeps provider events but must stop matching by lease id. |

## Launch And Reuse Cases To Preserve

### New local thread

Current:

- user may supply `cwd`
- thread row stores `cwd`
- local terminal initial cwd is `payload.cwd` or `LOCAL_WORKSPACE_ROOT`
- local runtime may skip volume sync when no volume exists

Target:

- create or select a workspace with `workspace_path = payload.cwd` or the local
  default workspace path
- set `agent.threads.current_workspace_id`
- sandbox/provider may be local and may not need provider env id

Open ruling:

- Whether a local thread can run with `current_workspace_id=NULL`. If allowed,
  every runtime/file path that requires a workspace must fail loudly instead of
  inventing a cwd fallback.

### New remote thread

Current:

- thread row stores selected provider as `sandbox_type`
- lease stores provider and recipe snapshot
- terminal initial cwd comes from provider default cwd
- volume is created early so upload can happen before sandbox creation

Target:

- create or select sandbox from provider/template
- create workspace under that sandbox with provider default workspace path or
  requested path
- set `agent.threads.current_workspace_id`
- store effective template/config on sandbox

Open ruling:

- File upload before sandbox creation needs a storage-first file channel
  contract. `current_workspace_id` can identify the workspace, but it does not
  by itself define where pending files live.

### Existing runtime reuse

Current:

- user selects existing `lease_id`
- service resolves ownership by walking lease -> terminal -> thread -> agent user
- new thread binds to same lease through terminal rows
- last successful config stores `lease_id`

Target:

- user selects existing `workspace_id`
- ownership resolves by `workspace.owner_user_id` and `thread.owner_user_id`
- new thread points `current_workspace_id` to that workspace
- last successful config stores `workspace_id`, not `lease_id`

Open ruling:

- Whether several threads can actively run against the same workspace
  concurrently. Target schema allows many threads to point to one workspace, but
  runtime locking/serialization is a product/runtime decision.

### Background command / async command

Current:

- background commands fork a new terminal from default terminal cwd/env state
- command lookup uses `terminal_commands` and `abstract_terminals`

Target:

- command execution should use sandbox exec API with workspace path and explicit
  cwd/env inputs
- command history location is not decided by this checkpoint

Open ruling:

- Where async command history lives: `agent.run_events`,
  `agent.thread_tasks`, observability, or runtime memory.

## Product-Ruling Edge Cases

These should not be hidden behind fallback code:

- Can a runnable thread have `current_workspace_id=NULL`?
- Can multiple active threads share one workspace concurrently?
- What happens to a running command when the user switches
  `current_workspace_id`?
- Is per-command cwd durable, or is cwd always supplied by each sandbox exec
  request?
- Is file-channel storage keyed by thread, workspace, or both?
- Does a workspace belong to exactly one sandbox forever, or can it migrate
  across sandboxes/devices?
- Should provider events attach to sandbox, workspace, or both?
- Should sync checksum state survive as internal runtime state, or disappear
  with volume sync?

## Why This Can Replace Terminal As Runtime Glue

Terminal currently carries four jobs:

1. thread-to-runtime binding
2. cwd/env state
3. command/session history
4. file-channel lookup through lease/volume

The target binding should only replace job 1:

```text
thread -> current_workspace_id -> workspace -> sandbox -> provider identity
```

The other three jobs need separate, smaller decisions:

- cwd/env state becomes explicit sandbox exec input plus workspace path
- command/session history moves to a chosen run/event/observability surface or
  remains ephemeral
- file channel moves to storage/upload-download contract

This separation is the point. Replacing terminal with a new "runtime session"
table that does all four jobs again would recreate the same abstraction under a
new name.

## First Implementation Checkpoint After This Preflight

Recommended next checkpoint:

`database-refactor-dev-replay-11-thread-runtime-binding-read-model`

Scope:

- Add a narrow read-model type and resolver for target-style
  `ThreadRuntimeBinding`.
- Prefer existing `agent.threads.current_workspace_id` when present.
- Keep legacy terminal/lease/volume paths untouched.
- Add tests for resolver behavior using fake repos:
  thread with workspace, thread without workspace, ownership mismatch, missing
  workspace, workspace with sandbox/provider facts.
- Do not route runtime execution through the resolver yet.
- Do not delete old repos or tables.
- Do not write migrations or live DB data.

Why this is the first code slice:

- It makes the new target binding concrete without changing runtime behavior.
- It creates a stable seam for later thread creation, file channel, monitor, and
  runtime manager cutovers.
- It avoids a deletion-first migration.
- It keeps product-ruling edge cases explicit and testable.

## Completion Checklist For This Preflight

- [x] Names the target binding path.
- [x] Shows current code still depends on terminal/lease/volume.
- [x] Defines resolver inputs and outputs.
- [x] Excludes terminal/chat_session/lease/volume ids from the target contract.
- [x] Maps current fields/tables to target fields/tables.
- [x] Lists launch/reuse cases that must be preserved.
- [x] Separates product-ruling edge cases from implementation fallbacks.
- [x] Identifies the first safe implementation checkpoint.
- [x] Preserves the no-code/no-DB/no-runtime stopline.
