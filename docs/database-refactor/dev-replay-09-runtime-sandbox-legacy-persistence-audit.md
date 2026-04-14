# Database Refactor Dev Replay 09: Runtime Sandbox Legacy Persistence Audit

## Goal

Classify the current runtime / sandbox persistence surfaces against the target
`container` design, then identify the first safe implementation checkpoint.

This checkpoint is audit-only. It does not delete repositories, change runtime
behavior, write live DB data, add migrations, edit terminal / volume code, or
continue schedule work.

## Sources

- Mycel target design repo:
  `/Users/lexicalmathical/Codebase/mycel-db-design`
- Target design commit inspected:
  `9422bd8b1f76f323605ad34240d57eecbddf5439`
- GitHub issue inspected:
  `nmhjklnm/mycel-db-design#1`
- Current Mycel base inspected:
  `origin/dev` at `ade4fc6320d9a4180f1aa575edcc23d3aa1eb256`

Design files inspected:

- `container-schema.md`
- `schema-decisions.md`
- `overview.md`

Current Mycel code inspected:

- `storage/contracts.py`
- `storage/container.py`
- `storage/runtime.py`
- `storage/providers/supabase/*`
- `sandbox/manager.py`
- `sandbox/capability.py`
- `sandbox/chat_session.py`
- `sandbox/sync/state.py`
- `sandbox/sync/strategy.py`
- `backend/web/routers/threads.py`
- `backend/web/services/file_channel_service.py`
- `backend/web/services/sandbox_service.py`
- `backend/web/services/monitor_service.py`
- `backend/web/services/resource_projection_service.py`

## Target Design Facts

The latest target design is centered on:

- `container.devices`
- `container.sandbox_templates`
- `container.sandboxes`
- `container.workspaces`
- `container.resource_snapshots`
- `container.provider_events`

Latest issue #1 resolution says:

- terminal persistence is deleted: no durable terminal entity, terminal pointer,
  command table, or command chunk table
- command execution should move to stateless no-PTY sandbox exec API
- volumes and `sync_files` are deleted from the design because upload/download
  should go through Supabase Storage rather than a volume abstraction
- `environment` naming is replaced by `sandbox`
- `library_recipes` becomes `container.sandbox_templates`
- `agent_registry` is legacy
- `tool_tasks` is renamed to `thread_tasks`
- `agent.schedules` and `agent.schedule_runs` stay in the target design

Important stale-design caveat:

- `overview.md` and `agent-schema.md` still contain `agent.tool_tasks` wording.
  Current Mycel already uses `agent.thread_tasks`.
- `schema-decisions.md` maps `sandbox_leases` to `container.sandboxes`, while
  `container-schema.md` maps old `sandbox_leases` semantics more closely to
  `container.workspaces`. The implementation checkpoint must follow the later
  concrete DDL: `devices -> sandboxes -> workspaces`.
- The first issue comment proposed adding mount / volume design, but the latest
  issue resolution explicitly deleted volumes / sync files. Treat the latest
  owner reply and commit `9422bd8` as newer authority.

## Current Inventory

| Current surface | Current tables | Main code refs | Target mapping | Classification | Reason |
|---|---|---|---|---|---|
| `TerminalRepo` | `abstract_terminals`, `thread_terminal_pointers` | `storage/contracts.py`, `storage/providers/supabase/terminal_repo.py`, `sandbox/manager.py`, `sandbox/capability.py`, `backend/web/services/thread_runtime_convergence.py` | deleted terminal layer; command execution through sandbox exec API | migrate later | Target says delete, but current runtime still uses terminal rows for thread binding, active terminal selection, cwd, command lookup, and monitor convergence. Deleting now would break thread runtime. |
| `ChatSessionRepo` | `chat_sessions`, `terminal_commands`, `terminal_command_chunks` | `storage/contracts.py`, `storage/providers/supabase/chat_session_repo.py`, `sandbox/chat_session.py`, `sandbox/capability.py`, `backend/web/services/file_channel_service.py` | no durable chat-session table; sandbox/workspace state + stateless exec | migrate later | Target says `chat_sessions` should already be gone, but current runtime still persists session lifecycle, async command metadata, command chunks, and thread activity. Needs exec-history decision before deletion. |
| `LeaseRepo` | `sandbox_leases`, `sandbox_instances` | `storage/providers/supabase/lease_repo.py`, `sandbox/lease.py`, `sandbox/manager.py`, `backend/web/services/sandbox_service.py` | `container.sandboxes` + `container.workspaces` | migrate later | This is the central old runtime state. It carries provider state, desired/observed state, recipe snapshot, instance id, and legacy `volume_id`. Mapping must be rewritten, not removed directly. |
| `SandboxVolumeRepo` | `sandbox_volumes`; `sandbox_leases.volume_id` | `storage/providers/supabase/sandbox_volume_repo.py`, `backend/web/routers/threads.py`, `backend/web/services/file_channel_service.py`, `sandbox/manager.py` | deleted; file channel should use storage/upload-download surface | migrate later | Target deletes volume semantics, but current thread creation eagerly creates volume + lease + terminal so uploads work before sandbox creation. `file_channel_service` still resolves `thread -> terminal -> lease -> volume_id -> sandbox_volumes`. |
| `SyncFileRepo` | `sync_files` | `storage/providers/supabase/sync_file_repo.py`, `sandbox/sync/state.py`, `sandbox/sync/strategy.py` | deleted | migrate later | Not a product-level file index, but not dead code: sync strategy still uses checksums for upload/download change detection. Replace with provider/storage-local sync state before deleting. |
| `RecipeRepo` | `library_recipes` | `storage/providers/supabase/recipe_repo.py`, `backend/web/services/library_service.py`, `backend/web/services/thread_launch_config_service.py`, `backend/web/routers/threads.py` | `container.sandbox_templates` | migrate later | Name and schema are wrong, but behavior is active: registration seeds default recipes, panel/library APIs CRUD recipes, and thread launch resolves owner-scoped recipe snapshots. |
| `ResourceSnapshotRepo` | `lease_resource_snapshots` | `storage/providers/supabase/resource_snapshot_repo.py`, `sandbox/resource_snapshot.py`, `storage/runtime.py` | `container.resource_snapshots` | migrate later | This is a straightforward table/domain rename once lease/workspace identity is settled. |
| `ProviderEventRepo` | `provider_events` | `storage/providers/supabase/provider_event_repo.py`, `sandbox/lease.py`, `backend/web/routers/webhooks.py` | `container.provider_events` | migrate later | Target keeps provider events. The repo should move schema/table identity, not disappear. |
| `SandboxMonitorRepo` | read projection over `chat_sessions`, `sandbox_leases`, `abstract_terminals`, `provider_events` | `storage/providers/supabase/sandbox_monitor_repo.py`, `backend/web/services/monitor_service.py`, `backend/web/services/resource_projection_service.py` | read projection over `container.sandboxes`, `container.workspaces`, `container.provider_events`, resource snapshots | migrate later | It is read-only, but it encodes the old join graph. Rewrite after the underlying persistence graph changes. |
| `AgentRegistryRepo` | `agent_registry` | `storage/providers/supabase/agent_registry_repo.py`, `core/agents/registry.py`, `core/agents/service.py`, `core/runtime/agent.py` | legacy; likely replaced by thread/task/run state plus in-memory child-agent tracking | needs product ruling | Design marks it legacy, but current agent service still records sub-agent lifecycle in it. Removing it is not a runtime/sandbox-only change and needs a separate agent-execution ruling. |
| `EvalRepo` / `EvalBatchRepo` | legacy eval tables | `storage/providers/supabase/eval_repo.py`, `storage/providers/supabase/eval_batch_repo.py` | observability/eval target to be added | keep temporarily | Out of this runtime/sandbox checkpoint. Eval needs its own schema checkpoint. |
| `agent.thread_tasks` | `agent.thread_tasks` | `storage/providers/supabase/tool_task_repo.py` | target `thread_tasks` | keep temporarily | Current code already uses the renamed target table even though design docs still contain stale `tool_tasks` wording. No action in this checkpoint. |
| `agent.schedules` / `agent.schedule_runs` | `agent.schedules`, `agent.schedule_runs` | `storage/providers/supabase/schedule_repo.py`, `backend/web/services/schedule_service.py` | target schedule tables | keep temporarily | PR #514 landed minimal storage/service. Schedule runtime is parked and should not distract this runtime/sandbox refactor. |

## Key Findings

### Terminal deletion is directionally right but not directly executable

The target design deletes terminal tables because no-PTY sandbox exec does not
need durable terminal identity. Current Mycel still uses terminal identity as
the glue between thread, lease, cwd, command history, monitor state, and file
channel. That means the implementation order must first introduce a thread /
workspace / sandbox binding that can carry the required runtime facts without a
terminal row.

Immediate terminal table deletion would be a behavior break, not cleanup.

### Volumes and sync files are separate migration problems

The target deletes both `volumes` and `sync_files`, but the current code uses
them for different jobs:

- `sandbox_volumes` is part of the app-layer file channel resolution path.
- `sync_files` is checksum state for provider sync strategy.

They should not be removed with one blind deletion checkpoint. The first needs a
new file channel contract. The second needs a new sync-state decision.

### Recipe should become template, not vanish

The old `library_recipes` name is wrong. The concept survives as
`container.sandbox_templates`.

Current code depends on recipe snapshots at thread launch and during auth
seeding. The safe migration is a table/repo/domain rename plus shape alignment,
not deletion.

### The live code is still built around the old chain

Current runtime chain in code is effectively:

```text
thread -> terminal -> lease -> instance
thread -> terminal -> lease -> volume -> file channel
chat session -> terminal -> command rows/chunks
lease -> resource snapshots/provider events
```

Target runtime chain should become:

```text
thread -> current_workspace_id -> workspace -> sandbox -> device/provider env
thread/workspace -> file channel via storage/upload-download contract
sandbox exec API -> optional run/event history, not terminal tables
sandbox/workspace -> resource snapshots/provider events
```

## What Not To Do Next

- Do not delete `TerminalRepo`, `ChatSessionRepo`, or `sandbox_volumes` first.
  They are legacy, but currently load-bearing.
- Do not spend more runtime effort on schedule. It is parked after PR #514.
- Do not treat `agent_registry` removal as part of the sandbox persistence
  checkpoint. It belongs to agent-execution lifecycle design.
- Do not invent another fallback compatibility layer. The next code slice
  should create the new binding surface, then cut consumers over.

## First Safe Implementation Checkpoint

Recommended next checkpoint:

`database-refactor-dev-replay-10-thread-workspace-sandbox-binding-preflight`

Scope:

- Add or align the minimal repository/service contract that lets runtime code
  resolve a thread to target-style workspace/sandbox facts without going through
  `abstract_terminals`.
- Keep old terminal/lease/volume repos intact during this slice.
- Add tests that prove the new resolver can represent current launch cases:
  new thread, existing lease/workspace reuse, provider name, cwd/workspace path,
  recipe/template snapshot id, and sandbox observed state.
- Do not delete old tables in this checkpoint.
- Do not add frontend behavior.
- Do not touch schedule.

Why this is the right first slice:

- It attacks the real dependency knot before deleting old tables.
- It gives later checkpoints a stable target interface.
- It avoids patch-style conditional deletion.
- It makes subsequent migrations mechanical:
  `file channel`, `sync state`, `exec command history`, `monitor projection`,
  and `recipe -> sandbox_template`.

Candidate follow-up checkpoints after 10:

1. `file-channel-storage-contract`: replace `thread -> terminal -> lease -> volume`
   file-channel resolution with the chosen storage/upload-download contract.
2. `sandbox-template-repo-cutover`: migrate `library_recipes` behavior to
   `container.sandbox_templates`.
3. `sandbox-monitor-projection-cutover`: rewrite monitor/resource read surfaces
   onto `container.sandboxes` / `container.workspaces`.
4. `stateless-exec-history-ruling`: decide whether command run history belongs
   in `agent.run_events`, `agent.thread_tasks`, observability, or ephemeral
   runtime memory.
5. `legacy-terminal-volume-deletion`: only after consumers no longer require
   terminal, chat session, volume, and sync-file tables.
