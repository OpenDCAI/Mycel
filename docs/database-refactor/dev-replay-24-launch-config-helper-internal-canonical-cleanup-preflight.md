# Database Refactor Dev Replay 24: Launch Config Helper Internal Canonical Cleanup Preflight

## Goal

Define the narrow internal cleanup slice that finishes the launch-config shell
rename inside backend helper truth.

This checkpoint is preflight only. It does not implement the rename yet.

## Why This Comes Next

Replay-23 already cleaned the outward shell contract:

- request/frontend contract now says `existing_sandbox_id`
- runtime/resource surfaces still honestly say `lease_id`

That leaves one internal residue:

- `backend/web/services/thread_launch_config_service.py` still uses
  `lease_id` as its helper-level canonical field
- `backend/web/routers/threads.py` still carries an outward/internal
  translation seam only because the helper layer has not caught up

So replay-24 is not a new feature lane. It is the internal completion pass for
the shell cleanup already in motion.

## Current Code Facts

### 1. Launch-config helper truth is still lease-shaped

`backend/web/services/thread_launch_config_service.py` still normalizes,
persists, validates, derives, and returns shell configs using `lease_id`.

Examples:

- `normalize_launch_config_payload(...)`
- `build_existing_launch_config(...)`
- `_validate_saved_config(...)`
- `_existing_config_from_lease(...)`
- `_derive_default_config(...)`

This is no longer aligned with the outward shell contract.

### 2. Route boundary still exists only to translate helper truth

`backend/web/routers/threads.py` currently contains:

- `_serialize_outward_shell_config(...)`
- `_serialize_internal_shell_config(...)`

Those helpers are not expressing business logic. They exist to translate
between:

- outward shell `existing_sandbox_id`
- helper-internal shell `lease_id`

That translation seam is now the most obvious remaining shell residue.

### 3. Runtime/resource lease identity is still legitimate and out of lane

Replay-20 through replay-23 already fenced this clearly:

- monitor/resource/session/terminal/lease surfaces that report real lease
  identity must keep `lease_id`
- replay-24 must not rename or reinterpret those fields

This lane is only about launch-config helper truth.

## Exact Target

Replay-24 should make backend helper truth use the same shell term as the
outward contract:

- helper-level shell config should use `existing_sandbox_id`
- route boundary translation should disappear if helper cleanup is sufficient

The intended end state is:

- outward shell contract: `existing_sandbox_id`
- backend helper shell contract: `existing_sandbox_id`
- runtime/resource identity: `lease_id`

## Exact Write Set

### Authorized backend code

- `backend/web/services/thread_launch_config_service.py`

### Authorized focused tests

- `tests/Integration/test_thread_launch_config_contract.py`

### Allowed only if RED proves strictly necessary

- `backend/web/routers/threads.py`
- `tests/Integration/test_threads_router.py`

Reason:

- the preferred landing is helper-only
- route edits are allowed only to remove now-unnecessary translation or to keep
  the save/load path honest after helper cleanup

## Planned Mechanism

Replay-24 should prefer a direct internal canonical rename, not alias sprawl.

### Step 1. Helper normalization becomes sandbox-shaped

`normalize_launch_config_payload(...)` should normalize to:

- `create_mode`
- `provider_config`
- `recipe_id`
- `existing_sandbox_id`
- `model`
- `workspace`

It should continue to enforce:

- `"new"` mode cannot carry an effective existing selector

### Step 2. Helper builders and validators follow the same canonical field

The following helper outputs and checks should stop emitting/expecting
shell-level `lease_id`:

- `build_existing_launch_config(...)`
- `build_new_launch_config(...)`
- `_validate_saved_config(...)`
- `_existing_config_from_lease(...)`
- `_derive_default_config(...)`

They may still resolve live lease rows by real `lease_id`, but the shell-shaped
config they return should now say `existing_sandbox_id`.

### Step 3. Remove route translation if helper cleanup fully covers it

If helper-level canonical cleanup lands cleanly, `threads.py` should no longer
need to translate:

- outward `existing_sandbox_id`
- internal `lease_id`

But replay-24 should remove that route seam only if the focused RED/GREEN proof
shows it is now dead weight.

## Recommendation

Prefer a true internal canonical rename, not a long-lived bilingual helper.

Do **not** do this:

- helper accepts/emits both `lease_id` and `existing_sandbox_id`
- route keeps permanent translation just in case

That would recreate the same residue one layer deeper.

## Test Plan

Replay-24 should be driven by focused contract proof.

Required coverage:

1. normalized `"existing"` helper payloads now use `existing_sandbox_id`
2. normalized `"new"` helper payloads still drop stray existing-selector input
3. saved/validated existing-mode configs still rebuild honestly from the live
   lease row, but the shell-shaped result now says `existing_sandbox_id`
4. derived default config from `thread.current_workspace_id` still works
5. route-level default-config save/load path remains correct if route cleanup is
   needed

Not required:

- frontend changes
- YATU browser proof
- runtime/provider proof
- SQL/migration/live DB proof

## Stopline

Replay-24 must not:

- touch monitor/resource/runtime lease identity
- rename `UserLeaseSummary.lease_id`
- rename `TerminalStatus.lease_id`
- rename `LeaseStatus.lease_id`
- change thread create truth
- change storage/runtime bindings
- widen into frontend/request contract work
- add aliases or fallback-heavy compatibility glue

## Expected Artifact

If replay-24 lands cleanly, the result should be easy to state:

- launch-config shell naming is internally and externally consistent
- route translation residue is gone or reduced to zero
- runtime/resource `lease_id` remains untouched

## Open Question For Ruling

Is replay-24 the right narrow checkpoint to finish the shell rename by making
`thread_launch_config_service.py` use `existing_sandbox_id` as its internal
canonical field, with route changes allowed only if focused RED proves they are
strictly necessary?
