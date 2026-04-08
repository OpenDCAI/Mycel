# Settings Persistence Contract Design

Date: 2026-04-08
Branch: `code-killer-settings-persistence`
Base: `draft/schema-redesign-placeholder`

## Problem

`backend/web/routers/settings.py` currently mixes three concerns in one file:

1. route contracts
2. storage-root selection (`user_settings_repo` vs filesystem json)
3. ad-hoc persistence transforms for workspace, models, observation, and sandbox settings

That glue is repeated across many endpoints:

- `_get_settings_repo()`
- `_try_get_user_id()`
- `_load_user_json()`
- `_load_models_for_user()`
- `_save_models_for_user()`
- repeated `repo + user_id` branching in route bodies

The result is not just verbosity. It also creates silent fallback behavior:

- some routes read from repo when available, otherwise silently read local files
- some routes write to repo when available, otherwise silently write local files
- auth extraction for optional repo-backed paths is repeated and easy to drift

This is a live persistence contract, not dead code.

## Scope

This seam only targets the persistence contract inside `backend/web/routers/settings.py`.

In scope:

- workspace settings persistence
- models settings persistence
- observation settings persistence
- sandbox settings persistence
- the repeated repo-vs-filesystem selection logic around those domains

Out of scope:

- response payload changes
- `/browse` and `/read` local path endpoints
- model hot-reload behavior in `/config`
- auth/JWT behavior changes
- changes to `user_settings_repo` storage schema
- front-end changes

## Current Facts

1. `get_settings()` reads workspace settings through one branch and model settings through another branch.
2. model-related endpoints repeatedly reconstruct the same `repo -> user_id -> load -> mutate -> save` flow.
3. observation and sandbox endpoints repeat similar repo/file branching with slightly different fallback behavior.
4. `_try_get_user_id()` is intentionally non-raising and makes repo-backed reads/writes optional.

## Approaches

### Option A: Router-local storage contract helper

Keep everything in `settings.py`, but collapse storage-root selection into a few explicit helpers:

- resolve current settings storage context once
- load/save workspace settings through one contract
- load/save models settings through one contract
- load/save observation settings through one contract
- load/save sandbox settings through one contract

Pros:

- smallest blast radius
- reduces repeated branching without creating a new module
- preserves current endpoint contracts

Cons:

- `settings.py` remains large
- logic is clearer, but still router-local

### Option B: Extract a dedicated settings persistence service

Move repo/filesystem branching into a new service module and keep routes thin.

Pros:

- strongest separation of responsibilities
- easiest future reuse

Cons:

- bigger hand-off surface
- risks adding one more contract layer without changing actual behavior
- higher chance of bureaucratic abstraction

### Option C: Leave structure as-is and trim locally

Only dedupe tiny fragments and keep branching inline in routes.

Pros:

- smallest immediate change

Cons:

- keeps the persistence contract fragmented
- does not address the repeated repo/file drift surface

## Recommendation

Choose **Option A**.

This seam is valuable because the problem is repeated persistence branching, not missing business capability. The smallest honest fix is to keep the contract router-local, shorten it, and make the storage-root choice explicit once per domain.

Creating a new service now would likely spend more code than it removes.

## Proposed Design

Add a router-local storage context helper that resolves:

- `repo`
- `user_id`
- whether repo-backed persistence is active for this request

Then add domain-specific helpers with one clear responsibility each:

- workspace load/save
- models load/save
- observation load/save
- sandbox config load/save

These helpers must preserve current outward route behavior:

- same status codes
- same payload shapes
- same route-level semantics

They should only centralize storage-root selection and persistence transforms.

## Fail-Loud Rule

This seam should reduce silent fallback, not deepen it.

Rules:

1. If a helper is called in repo-backed mode, it should not silently drift into an unrelated filesystem write path unless that route already intentionally supports that fallback today.
2. Existing route semantics that intentionally support filesystem mode must remain explicit in the helper, not hidden by broad `except Exception`.
3. No new backward-compat fallback paths.

## Testing Strategy

Prefer extending existing storage wiring tests and route tests over adding a large new integration suite.

Proof should cover:

1. repo-backed settings read path still works
2. filesystem mode still works where currently intended
3. workspace/default-model/model-mapping/custom-model/provider/observation/sandbox endpoints keep current response contracts
4. no route begins silently writing to a different persistence root than before

## Stopline

Do not turn this into a settings API redesign.

Specifically do not:

- rename or reshape endpoint responses
- merge workspace and models semantics into one shared write model
- touch `/browse` or `/read`
- touch `/config` hot-reload logic
- introduce a new external service contract unless router-local helpers prove insufficient

## Success Criteria

This seam is successful if:

1. repeated repo-vs-filesystem branching is materially shorter
2. persistence behavior is more explicit and less drift-prone
3. no outward settings contract changes
4. total complexity goes down, not up
