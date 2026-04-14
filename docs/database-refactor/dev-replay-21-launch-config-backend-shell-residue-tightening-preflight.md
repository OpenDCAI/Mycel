# Database Refactor Dev Replay 21: Launch Config Backend Shell Residue Tightening Preflight

## Goal

Define the first backend-only implementation slice that tightens launch-config
shell residue without changing request/frontend payload shape.

This checkpoint is preflight only. It does not implement the tightening yet.

## Why This Comes Next

Replay-20 closed the classification question:

- shell-level `lease_id` in thread-create / launch-config surfaces is residue,
  not backend authority
- runtime/resource `lease_id` identity is a separate category and out of lane

That means the next slice should not yet rename request fields or rewrite the
frontend shell. It should first make backend shell semantics more honest while
the payload shape remains temporarily stable.

## Current Code Facts

### 1. Backend normalization still allows `lease_id` to survive independent of `create_mode`

`backend/web/services/thread_launch_config_service.py`
`normalize_launch_config_payload(...)` currently returns:

- normalized `create_mode`
- normalized `lease_id`

But it does not enforce the shell truth that:

- `"new"` config should not carry an effective existing-lease selector

So a `"new"` payload can still persist a trimmed `lease_id` through the generic
normalization path.

### 2. Existing-mode truth is already materialized from live lease lookup

The same service already does something more honest in other paths:

- `_validate_saved_config(...)` resolves `"existing"` configs through live
  lease lookup
- `_existing_config_from_lease(...)` rebuilds canonical existing config from
  the actual lease row
- `_derive_default_config(...)` derives existing-mode defaults from thread-owned
  `current_workspace_id`

So replay-21 is not inventing a new principle. It is tightening the remaining
backend shell path to match what the rest of the service already implies.

### 3. Existing route save path already uses backend helpers

`backend/web/routers/threads.py` uses:

- `build_existing_launch_config(...)`
- `build_new_launch_config(...)`
- `save_last_successful_config(...)`

That means a backend-only service tightening may be enough if it stays inside
the helper layer. Router changes should be avoided unless the tests prove they
are required.

## Exact Target

Replay-21 should tighten backend shell semantics so that:

- `"new"` launch-config state cannot carry an effective `lease_id`
- `"existing"` launch-config state still uses `lease_id` only as shell-level
  selector / round-trip field
- canonical existing-mode config continues to be rebuilt from the resolved
  lease row, not trusted raw payload

## Exact Write Set

### Authorized code

- `backend/web/services/thread_launch_config_service.py`

### Authorized focused tests

- `tests/Integration/test_thread_launch_config_contract.py`

### Allowed only if RED proves strictly necessary

- `backend/web/routers/threads.py`

Reason:

- the tightening should ideally land in backend helper/service semantics only
- router widening should happen only if helper-level tightening exposes a real
  mismatch in the current save/create path

## Planned Mechanism

Replay-21 should prefer the smallest honest change:

1. make normalization and/or save-path semantics enforce:
   - if `create_mode == "new"`, persisted/canonical config has `lease_id = None`
2. preserve existing-mode shell shape for now:
   - `lease_id` may still exist as selector/round-trip field
3. keep derived existing-mode defaults sourced from thread-owned bridge truth
4. do not change request models or frontend payloads yet

## Candidate Tightening Points

The likely narrowest landing is one of:

### Option A: tighten `normalize_launch_config_payload(...)`

If `create_mode` normalizes to `"new"`, force:

- `lease_id = None`

Pros:

- smallest single-point rule
- directly expresses backend shell truth

### Option B: tighten save/validate paths only

Leave raw normalization generic, but force `"new"` configs to lose `lease_id`
before persistence and canonicalization.

Pros:

- narrower effect surface

Cons:

- easier to leave duplicate shell looseness elsewhere

## Recommendation

Prefer Option A unless RED proves it breaks an intentional backend caller.

Reason:

- replay-21 is about making backend shell semantics explicit
- the cleanest place to express that rule is the normalization helper itself

## Test Plan

Replay-21 should be driven by focused tests in
`tests/Integration/test_thread_launch_config_contract.py`.

Required coverage:

1. a `"new"` payload with a stray `lease_id` is normalized/persisted/canonicalized
   with `lease_id = None`
2. existing-mode canonical shape still carries `lease_id` from the resolved
   lease row
3. replay-15 existing-mode derivation from thread-owned bridge still passes
4. route-level successful-config persistence still stays correct for existing
   and new paths

## Stopline

Replay-21 must not:

- rename request model fields
- change frontend payload/types
- change monitor/runtime/resource surfaces
- change storage contracts
- change runtime binding readers
- add SQL/migrations/live DB writes
- remove existing-mode shell support entirely

## Expected Artifact

If replay-21 lands cleanly, the result should be easy to state:

- backend shell semantics no longer let `"new"` configs carry an effective
  `lease_id`
- existing-mode shell support still works
- request/frontend contract remains temporarily unchanged

## Open Question For Ledger Ruling

Is this the right narrow replay-21 boundary:

- helper/service-only by default
- `thread_launch_config_service.py` plus focused integration proof
- backend-shell tightening first, while request/frontend payload shape stays
  stable for now?
