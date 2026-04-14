# Database Refactor Dev Replay 18: Legacy Current Workspace Read Fencing Preflight

## Goal

Decide how the post-replay-17 system should fence the remaining
`thread.current_workspace_id = NULL` residue on the read side.

This checkpoint is doc/ruling only. It does not change storage contracts,
router behavior, frontend payloads, runtime managers, SQL/migrations, or live
DB state.

## Why This Comes Next

Replay-17 already enforced the write-side truth:

- newly created runnable thread writes must carry a non-blank
  `current_workspace_id`
- child-thread creation now fails loudly instead of silently propagating a
  missing bridge

That means the next ambiguity is no longer "should new writes allow null?".
That question is settled.

The remaining ambiguity is narrower:

- where is `current_workspace_id = NULL` still tolerated today?
- which of those sites are honest historical/read-compat residue?
- which are just test or helper looseness that still makes null look more
  normal than it really is?

## Linkage

- replay-13 made supported owner-facing thread creation write
  `current_workspace_id`
- replay-15 made backend default resolution depend on thread-owned bridge
  truth
- replay-16 ruled that null is no longer target truth for newly created
  runnable threads
- replay-17 enforced that write-side invariant

So replay-18 should not go back to router/API proof or create-path mechanics.
It should fence the leftover read-side residue honestly.

## Current Code Facts

### 1. The structural row contract still admits legacy null

`storage/contracts.py` still defines:

- `ThreadRow.current_workspace_id: str | None = None`

That is now best understood as a legacy/read-compat concession, not a target
write contract.

### 2. Repo read paths still accept historical null rows

`tests/Unit/storage/test_supabase_thread_repo.py` includes
`test_supabase_thread_repo_reads_agent_threads_schema_table`, which reads an
`agent.threads` row where:

- `current_workspace_id = None`

This is an honest read-compat proof. It models a historical row, not a new
write target.

### 3. Runtime binding read seam already treats missing bridge as a hard error

`tests/Unit/backend/web/services/test_thread_runtime_binding_service.py`
contains `test_missing_workspace_pointer_fails_loudly`, which proves:

- a thread row with `current_workspace_id = None` is not runnable binding
  truth
- the read seam raises immediately instead of inventing fallback binding

This is not residue to remove. It is the correct fence.

### 4. Some test scaffolding still keeps null-looking create shapes looser than production

`tests/Unit/core/test_agent_service.py` still uses a `_FakeThreadRepo.create`
helper with:

- `current_workspace_id: str | None = None`

Production repo contract has already moved tighter in replay-17. This helper
shape is now broader than the real write boundary.

The specific replay-17 negative test that feeds a parent row with
`current_workspace_id = None` is still honest, because it is modeling a legacy
read row. But the helper signature itself is now suspiciously permissive.

## Explicit Site Classification

Replay-18 should not talk about "legacy null residue" abstractly. The remaining
sites should be classified explicitly.

### Intentionally legal legacy/read-compat sites

These sites are still acceptable for now because they are either structural
read-compat concessions or explicit legacy-row proof:

1. `storage/contracts.py`

- `ThreadRow.current_workspace_id: str | None = None`
- reason: the row model still has to admit historical storage state on read
- not permission for new create paths to omit the bridge

2. `tests/Unit/storage/test_supabase_thread_repo.py`

- `test_supabase_thread_repo_reads_agent_threads_schema_table`
- legacy row fixture contains `current_workspace_id = None`
- reason: proves repo read compatibility with an old stored row

3. `tests/Unit/backend/web/services/test_thread_runtime_binding_service.py`

- `test_missing_workspace_pointer_fails_loudly`
- fixture passes `current_workspace_id = None`
- reason: proves a legacy row is not silently upgraded into runnable truth

4. `tests/Unit/core/test_agent_service.py`

- `test_handle_agent_does_not_register_child_thread_when_parent_bridge_is_missing`
- parent-thread fixture contains `current_workspace_id = None`
- reason: explicit negative proof that a legacy parent row cannot seed a new
  child thread write

### Suspicious helper/test looseness

These sites are not honest legacy-row fixtures. They make null look broader
than production truth and are the likely first replay-19 targets:

1. `tests/Unit/core/test_agent_service.py`

- `_FakeThreadRepo.create(..., current_workspace_id: str | None = None)`
- reason it is suspicious: this is a general-purpose create helper, while the
  production create contract after replay-17 requires a bridge
- preferred future shape: helper create contract should require a bridge, while
  tests that need legacy rows should construct those rows explicitly in the
  backing `rows` map instead of inheriting permissiveness from the create API

### Out of lane for replay-18

These are real residues, but not part of the current-workspace legacy read
fence lane:

- lease-shaped launch-config/request/frontend shell residue
- router/API create-path proof already covered by existing integration tests
- historical DB repair or backfill

## The Actual Ambiguity

There are two different things mixed together under "null still exists":

### A. Honest historical/read-compat residue

Examples:

- reading an old thread row from storage
- proving that runtime binding fails loudly when that old row lacks a bridge
- negative tests that intentionally simulate a legacy parent row

### B. Residue that still normalizes null too much

Examples:

- fake repos/helpers whose create signatures still imply null is an ordinary
  new-write option
- broad test scaffolding that does not distinguish "legacy row fixture" from
  "normal thread shape"

Replay-18 should separate A from B explicitly.

## Recommended Ruling

### 1. Keep legacy null support only where the system is explicitly modeling old rows

The system should still permit `current_workspace_id = None` only in places
that are clearly about:

- historical storage compatibility
- negative/failure-path proof for old rows
- read-only fixtures that intentionally represent legacy DB state

### 2. Stop letting general-purpose helpers imply that null is still a normal thread-create shape

Helpers and test doubles that model thread creation should converge toward the
post-replay-17 truth:

- create path requires a bridge

If a test needs a null row, it should create that as an explicit legacy row
fixture, not inherit it accidentally from a permissive create helper.

### 3. Do not spend replay-18 on router/API proof

`tests/Integration/test_threads_router.py` already proves the owner-facing
router writes `current_workspace_id` for:

- existing lease create path
- new sandbox create path

Replaying that proof again would not reduce a real ambiguity.

### 4. Do not spend replay-18 on launch-config shell cleanup

Lease-shaped shell residue is real, but it belongs to a different line of
work. It should not be mixed into the current-workspace legacy fence lane.

## Proposed First Implementation Checkpoint After Replay-18

`database-refactor-dev-replay-19-legacy-current-workspace-read-fence-enforcement`

Target boundary:

- tighten test doubles / helper contracts so they stop implying null is a
  normal create shape
- preserve explicit historical-row fixtures where needed
- keep runtime binding failure-path proof intact
- keep repo read-compat proof intact until there is a separate historical
  cleanup / migration decision

## Candidate Write Set For Replay-19

These files look like the likely narrowest first slice:

- `tests/Unit/core/test_agent_service.py`
- any local helper class inside that file or neighboring unit helper files

Possibly, but only if truly needed after inspection:

- `storage/contracts.py`
- read-model or helper-level tests that currently blur "legacy row fixture"
  vs "normal row"

Replay-18 does **not** authorize those edits. It only proposes the direction.

## Stopline

Replay-18 does **not** authorize:

- router changes
- frontend/request payload changes
- launch-config redesign
- runtime cutover
- SQL/migrations/live DB writes
- historical row backfill/repair
- removing read compatibility for old null rows

## Expected Artifact

If this preflight is accepted, the result should be easy to state:

- new-write truth remains strict after replay-17
- historical null rows remain readable only as explicit legacy residue
- tests/helpers stop pretending null is still a normal create shape

## Open Question For Ledger Ruling

Is the right next move:

- keep `ThreadRow.current_workspace_id` structurally optional for explicit
  legacy/read compatibility
- but start tightening test doubles and helper contracts so null survives only
  inside deliberately labeled historical-row fixtures?
