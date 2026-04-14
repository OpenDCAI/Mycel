# Database Refactor Dev Replay 16: Current Workspace Invariant Preflight

## Goal

Decide whether `thread.current_workspace_id` may remain structurally optional,
or whether the post-replay-13 system is ready to require it for all newly
created runnable threads.

This checkpoint is doc/ruling only. It does not change storage contracts, repo
implementations, routers, frontend behavior, runtime managers, SQL/migrations,
or live DB state.

## Why This Comes Before Shell Cleanup

There are still lease-shaped residues in the create/default-config shell.
Those are real, but they are not the most important ambiguity now.

The deeper unresolved question is structural:

- is `current_workspace_id` still optional because the architecture needs that,
  or only because legacy residue has not been fully fenced?

If this is not answered first, later shell cleanup can collapse into naming
work while the underlying thread contract stays ambiguous.

## Linkage

- replay-10 established the thread/workspace/sandbox binding direction
- replay-11 added the read seam for runtime binding
- replay-13 made supported thread-create paths write `current_workspace_id`
- replay-15 moved backend launch-config default discovery to thread-owned
  `current_workspace_id`

So by replay-15, the thread-side bridge is already authoritative in two places:

- thread creation
- derived backend default resolution

That raises the question of whether structural optionality is still honest.

## Sources

- `storage/contracts.py`
- `storage/providers/supabase/thread_repo.py`
- `backend/web/routers/threads.py`
- `core/agents/service.py`
- `tests/Unit/storage/test_supabase_thread_repo.py`
- `tests/Integration/test_threads_router.py`
- `tests/Unit/core/test_agent_service.py`
- `docs/database-refactor/dev-replay-10-thread-workspace-sandbox-binding-preflight.md`
- `docs/database-refactor/dev-replay-12-thread-create-write-contract-preflight.md`
- `docs/database-refactor/dev-replay-14-launch-config-backend-truth-preflight.md`
- `docs/database-refactor/dev-replay-15-launch-config-backend-default-resolution-preflight.md`

## Current Code Facts

### 1. The structural row contract still says `current_workspace_id` is optional

`storage/contracts.py` currently defines:

- `ThreadRow.current_workspace_id: str | None = None`

That means the repo/domain contract still permits thread rows without a bridge.

### 2. The write contract also still allows omission

`storage/contracts.ThreadRepo.create(...)` and
`storage/providers/supabase/thread_repo.py` still accept:

- `current_workspace_id: str | None = None`

and `SupabaseThreadRepo.create(...)` writes that value straight through without
requiring it.

### 3. Replay-13 already made supported create paths write the bridge

`backend/web/routers/threads.py` now writes:

- existing lease path -> `current_workspace_id = selected_lease_id`
- new sandbox path -> `current_workspace_id = _create_thread_sandbox_resources(...)`

So the main owner-facing thread-create flow already behaves as if the bridge is
required for runnable thread creation.

### 4. Child-thread creation also propagates a bridge

`core/agents/service.py` currently creates child thread metadata with:

- `current_workspace_id = parent_thread.get("current_workspace_id")`

So subagent thread creation already assumes a bridge-bearing parent and carries
that bridge forward.

### 5. Tests still tolerate null bridge rows as legacy shape

There are still tests that admit `current_workspace_id = None` as a valid row
shape, which reflects historical compatibility rather than newly justified
target behavior.

## The Actual Ambiguity

There are two different interpretations of today's optionality:

### Interpretation A: Optionality is still architecturally legitimate

This would mean:

- there are still newly created runnable thread classes that honestly do not
  have a bridge at creation time
- null remains part of the intended target contract

### Interpretation B: Optionality is only legacy residue

This would mean:

- newly created runnable threads should carry a bridge
- null survives only because older rows/tests/contracts have not been fenced
  yet

Replay-13 and replay-15 strongly suggest B, not A.

## Ruling

### 1. For newly created runnable threads, bridge optionality now looks like residue, not target truth

Current evidence favors this conclusion:

- the owner-facing create path already writes the bridge
- child-thread creation already propagates the bridge
- backend default discovery already depends on thread-owned bridge truth

So `current_workspace_id = NULL` no longer looks like a healthy target state
for newly created runnable thread rows.

### 2. Structural optionality may remain temporarily for read compatibility only

Replay-16 does **not** require immediate global non-null enforcement.

It only says:

- optionality is no longer justified as the intended write target for new
  runnable threads
- if null remains, it should be fenced as legacy/read-compat residue rather
  than presented as a normal new-write state

### 3. Null is no longer acceptable for newly created runnable thread classes

Replay-16 should treat these thread classes as requiring a bridge:

- owner-facing newly created threads from `backend/web/routers/threads.py`
- subagent/child threads created from `core/agents/service.py`

Replay-16 should treat null as still tolerated only for:

- pre-replay historical rows already stored without a bridge
- read-only compatibility fixtures/tests that intentionally model those
  historical rows

Replay-16 does **not** identify any newly created runnable thread class that
still honestly requires `current_workspace_id = NULL`.

### 4. The next implementation slice should target write-side enforcement first, not historical cleanup

The first implementation after this preflight should focus on:

- enforcing bridge presence for new runnable thread creation paths that are
  already expected to have one
- tightening tests/contracts around that truth

It should **not** start by:

- backfilling old rows
- running migrations
- cleaning historical DB residue
- widening into shell/frontend cleanup

### 5. This preflight does not answer whether the field name is ideal

`current_workspace_id` may still be an imperfect bridge name. That is a
separate question.

Replay-16 is only about invariant truth:

- should new runnable threads be allowed to omit it?

The current answer is: probably no.

## Proposed First Implementation Checkpoint After Replay-16

`database-refactor-dev-replay-17-current-workspace-invariant-enforcement`

Target boundary:

- tighten thread write contracts so newly created runnable thread paths fail
  loudly if they attempt to create a row without a bridge
- update focused tests accordingly
- keep historical row cleanup, migrations, and frontend/shell work out of scope

## Stopline

Replay-16 does **not** authorize:

- changing `ThreadRow` or repo signatures yet
- router implementation changes
- child-thread implementation changes
- frontend/request-shell cleanup
- runtime cutover
- SQL/migrations/live DB writes
- historical data repair

## Honest Residuals

- `ThreadRow.current_workspace_id` is still typed optional
- repo create signatures still allow omission
- some tests still tolerate null bridge rows
- old rows may still exist without a bridge

Those residuals are now explicit. The next slice should determine whether new
write paths are allowed to keep pretending that null is a normal target state.
