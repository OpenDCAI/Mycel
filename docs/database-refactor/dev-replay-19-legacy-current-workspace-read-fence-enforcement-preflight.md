# Database Refactor Dev Replay 19: Legacy Current Workspace Read Fence Enforcement Preflight

## Goal

Tighten the remaining general-purpose test helper shape so it stops implying
that `current_workspace_id = NULL` is still a normal create-path option.

This checkpoint is preflight only. It does not implement the tightening yet.

## Why This Comes Next

Replay-18 closed the doc/ruling question:

- explicit historical/read-compat null rows are still legal
- permissive general-purpose create helpers are not

That means the next implementation slice should not revisit architecture or
router proof. It should remove the smallest remaining place where tests still
normalize nullable create semantics more than production does.

## Linkage

- replay-17 enforced the production write-side invariant: new runnable thread
  writes require a bridge
- replay-18 classified remaining null-tolerant sites and identified the first
  suspicious helper looseness

So replay-19 should be the first narrow enforcement slice on the test/helper
side.

## Current Code Fact

`tests/Unit/core/test_agent_service.py` still defines:

- `_FakeThreadRepo.create(..., current_workspace_id: str | None = None)`

That helper is broader than the post-replay-17 production contract.

At the same time, the same test file also contains an honest legacy-row
negative proof:

- `test_handle_agent_does_not_register_child_thread_when_parent_bridge_is_missing`

That test does **not** need a nullable create helper. It only needs an
explicitly seeded historical parent row in `rows={...}` with
`current_workspace_id = None`.

So the helper can tighten without losing the legacy negative proof.

## Exact Target

Replay-19 should enforce this narrow truth:

- general-purpose thread-create test helpers should require a concrete
  `current_workspace_id`
- tests that need a legacy null row should construct that row explicitly as a
  stored fixture, not via a permissive create API

## Exact Write Set

### Authorized files

- `tests/Unit/core/test_agent_service.py`

### Not authorized unless a new ruling proves it is necessary

- `storage/contracts.py`
- `storage/providers/supabase/thread_repo.py`
- `core/agents/service.py`
- router files
- frontend files

Reason:

- replay-19 is meant to fence helper/test looseness first
- widening into production contracts would be churn unless the narrow test-only
  slice proves insufficient

## Planned Mechanism

Replay-19 should prefer the smallest honest change:

1. tighten `_FakeThreadRepo.create(...)` so helper callers must provide a
   concrete bridge
2. update happy-path tests in the same file to pass explicit
   `current_workspace_id`
3. leave legacy-row negative proof intact by continuing to seed historical rows
   directly in `rows={...}` fixtures
4. do not add fallback or auto-filled fake bridges in test helpers

## Test Plan

Replay-19 should stay inside focused unit proof in
`tests/Unit/core/test_agent_service.py`.

Required checks:

1. existing happy-path child-thread registration proof still passes with an
   explicit bridge-bearing helper create path
2. the negative proof for legacy parent row with
   `current_workspace_id = None` still passes
3. no other tests in that file silently rely on nullable helper-create
   semantics

No product/runtime/YATU claim is expected from replay-19.

## Expected Artifact

If replay-19 is implemented cleanly, the result should be easy to state:

- production write truth stays unchanged
- legacy null rows remain available only as explicit stored fixtures
- the general-purpose create helper in `test_agent_service` no longer suggests
  that null is a normal create shape

## Stopline

Replay-19 must not:

- change production code
- change storage contracts
- change router/API behavior
- touch launch-config/frontend shell residue
- change runtime cutover behavior
- add SQL/migrations/live DB writes
- remove explicit legacy-row negative proofs

## Open Question For Ledger Ruling

Is this narrow replay-19 boundary acceptable:

- tighten only `tests/Unit/core/test_agent_service.py`
- keep the change test/helper-only unless the slice proves insufficient
- preserve explicit historical-row fixtures as the only remaining intentional
  nullable shape in this lane?
