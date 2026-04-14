# Database Refactor Dev Replay 17: Current Workspace Invariant Enforcement Preflight

## Goal

Define the exact write-side enforcement slice that follows replay-16:

- newly created runnable thread writes must fail loudly when the bridge is
  missing
- historical read compatibility for already-null rows stays out of scope

This checkpoint is preflight only. It does not implement the enforcement.

## Linkage

- replay-13 made supported owner-facing thread creation write
  `current_workspace_id`
- replay-15 made backend default discovery depend on thread-owned bridge truth
- replay-16 ruled that for newly created runnable threads,
  `current_workspace_id = NULL` is no longer target truth, only
  legacy/read-compat residue

So replay-17 is the first write-side enforcement slice:

- stop treating null as a normal new-write state
- do not yet widen into historical repair or shell/frontend cleanup

## Exact Target

Replay-17 should enforce this invariant:

- any newly created runnable thread row must provide a non-blank
  `current_workspace_id`

This applies to the currently known new-write runnable thread classes:

- owner-facing thread creation from `backend/web/routers/threads.py`
- subagent/child thread creation from `core/agents/service.py`

This checkpoint does **not** require:

- rewriting historical rows
- changing read models so old rows stop loading
- renaming the field

## Exact Write Set

### Authorized code

- `storage/contracts.py`
- `storage/providers/supabase/thread_repo.py`
- `core/agents/service.py`

### Authorized focused tests

- `tests/Unit/storage/test_supabase_thread_repo.py`
- `tests/Unit/core/test_agent_service.py`

### Allowed if strictly required, but only with Ledger re-check if widened

- `backend/web/routers/threads.py`
- `tests/Integration/test_threads_router.py`

Reason:

- current owner-facing router paths already appear to compute a bridge before
  write
- replay-17 should ideally prove that by tightening the repo contract first
- only if enforcement reveals a real router gap should the router/test pair
  enter the slice

## Planned Mechanism

Replay-17 should prefer the smallest honest enforcement:

1. make thread-create contract require a non-blank bridge for new writes
2. make `SupabaseThreadRepo.create(...)` fail loudly if
   `current_workspace_id` is blank/null
3. keep read-side row loading unchanged for existing historical null rows
4. tighten child-thread creation expectations so missing parent bridge is not
   silently propagated into a new child row

The intended failure shape is:

- storage/repo boundary raises immediately for missing bridge
- callers do not invent fallback bridges
- if a caller cannot supply a bridge, that path is not ready and must be fixed
  or explicitly excluded

## Candidate Enforcement Shape

The preferred shape is:

- `ThreadRepo.create(...)` requires `current_workspace_id: str`
- `SupabaseThreadRepo.create(...)` validates non-blank bridge and raises
  `ValueError`
- `ThreadRow.current_workspace_id` may remain structurally optional for now if
  that is still needed for historical read compatibility

This keeps replay-17 focused on write-side truth instead of pretending old data
has already been repaired.

## Test Plan

Replay-17 should be driven by focused RED/GREEN tests in the authorized unit
files.

Required coverage:

1. `SupabaseThreadRepo.create(...)` fails loudly when
   `current_workspace_id` is omitted or blank
2. existing positive repo create path with a concrete bridge still passes
3. child-thread registration path fails or refuses to create when parent thread
   lacks a bridge
4. existing child-thread happy path with inherited bridge still passes

Optional router proof is only needed if repo enforcement exposes a real gap in
the current owner-facing path.

## Stopline

Replay-17 must not:

- backfill historical rows
- change read-side loading of historical null rows
- redesign frontend/request-shell semantics
- change launch-config payload shape
- change runtime binding readers/managers
- add migrations or live DB writes
- widen into monitor/file-channel/schedule work
- add fallback logic that fabricates or guesses a bridge

## Expected Artifact

If replay-17 is authorized and implemented cleanly, the result should be easy
to state:

- new runnable thread writes now require a bridge
- historical reads still tolerate old null rows
- no shell/frontend/runtime scope was widened

## Open Question For Ledger Ruling

Is the preferred enforcement shape acceptable:

- tighten `ThreadRepo.create(...)` and `SupabaseThreadRepo.create(...)`
  immediately
- keep `ThreadRow.current_workspace_id` structurally optional for now as a
  read-compat concession

This is the narrowest path I see that matches replay-16 without pretending old
rows are already gone.
