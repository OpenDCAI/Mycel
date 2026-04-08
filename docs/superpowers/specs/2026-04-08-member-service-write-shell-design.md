# Member Service Write Shell Cleanup

## Goal

Remove the legacy filesystem shell from `backend/web/services/member_service.py` write/update paths for repo-backed agent users, without changing outward member payloads and without mixing marketplace lineage into the same cut.

## Current Facts

The read-side contract is already largely repo-rooted:

- `list_members(owner_user_id=..., user_repo=..., agent_config_repo=...)` reads from repos
- unscoped `list_members()` already returns builtin-only `__leon__`
- `get_member("__leon__")` is already a builtin local island
- generic `get_member(member_id, ...)` already resolves through `user_repo + agent_config_repo`

The remaining filesystem shell is on the write/update side:

- `update_member()` still branches on `MEMBERS_DIR / member_id`
- `update_member_config()` still writes local files when the member dir exists
- `publish_member()` still reads and writes `meta.json` when the member dir exists
- `delete_member()` still removes local member dirs when present

This means a repo-backed agent user can still drift through a legacy local shell if the old member dir happens to exist.

## In Scope

- `update_member()` write path selection
- `update_member_config()` write path selection
- `publish_member()` version/status update selection
- `delete_member()` delete path selection for repo-backed agent users
- Tests that prove repo-backed agent users stay repo-rooted even when legacy member dirs exist

## Out Of Scope

- Marketplace lineage root replacement
- `install_from_snapshot()` filesystem layout
- `__leon__` builtin local island
- Outward member payload shape
- Any new backward-compat fallback
- Full deletion of filesystem helper utilities used by snapshot install/import

## Approaches Considered

### A. Minimal branch priority flip

Keep all legacy filesystem branches, but prefer repo-backed branches whenever `user_repo + agent_config_repo` resolve the agent user.

Pros:

- smallest blast radius
- preserves legacy-only flows for snapshots/imports

Cons:

- leaves dead-looking filesystem branches in live write functions
- contract remains less obvious

### B. Recommended: repo-first write shell cut

For agent users with `user_repo + agent_config_repo`, route `update_member`, `update_member_config`, `publish_member`, and `delete_member` through repo-rooted logic even if `MEMBERS_DIR / member_id` exists.

Keep filesystem writes only for paths that are still explicitly local artifacts:

- builtin/local install/import shells
- snapshot/layout materialization that is still intentionally filesystem-backed

Why this cut:

- it removes the real contract ambiguity
- it does not require marketplace lineage work
- it stays inside `member_service`

### C. Full member filesystem purge

Delete all remaining filesystem writes from `member_service`.

Rejected:

- too broad
- collides with marketplace install/import residuals
- likely mixes lineage and local artifact policy into one PR

## Target Contract

1. If a member resolves to an agent user with `agent_config_id`, write/update/publish/delete operations use repo-rooted state as the source of truth.
2. The existence of `MEMBERS_DIR / member_id` must not silently change behavior for repo-backed agent users.
3. Legacy filesystem materialization can remain only where it is still an explicit local artifact concern.
4. `__leon__` stays read-only.
5. Errors stay loud; no fallback from missing repo state back into member-dir writes.

## Design

### 1. Resolve agent-user identity before testing filesystem presence

For `update_member`, `update_member_config`, `publish_member`, and `delete_member`, first resolve:

- `user = user_repo.get_by_id(member_id)` when repos are available
- whether that user has `agent_config_id`

If the user resolves as a repo-backed agent, treat repo state as canonical and do not branch into legacy member-dir behavior just because the directory exists.

### 2. Keep filesystem only for explicit local-artifact paths

Do not rip out helper functions like `_write_rules()` or `_write_sub_agents()` yet.

They still serve snapshot/install/import flows.

The cut is narrower:

- repo-backed agent users do not use them for normal panel/publish/delete mutations
- local artifact paths can remain until marketplace lineage / install cleanup is handled separately

### 3. Publish must stop deriving parent/version lineage from legacy member dir for repo-backed agents

For repo-backed users, `publish_member()` should use repo-backed config/status/version inputs.

If local `meta.json` exists, it must not outrank repo state for the live agent contract.

This is still not full marketplace-lineage replacement; it only removes legacy member-dir priority from `member_service` publish behavior.

### 4. Delete must treat repo-backed agent user as a repo object first

Delete the repo config and user row as the canonical operation.

If a legacy dir exists, its removal is cleanup, not the decision point for whether the member exists.

## Proof Plan

### Contract proof

- repo-backed `update_member()` still works when a legacy member dir exists, without reading it as the source of truth
- repo-backed `update_member_config()` still works when a legacy member dir exists, without round-tripping through `AgentLoader().load_bundle(member_dir)`
- repo-backed `publish_member()` updates repo status/version even if a legacy member dir exists
- repo-backed `delete_member()` succeeds based on repo/user existence, not on member-dir existence

### Regression proof

- existing cutover tests remain green
- add only the smallest missing tests for legacy-dir-present repo-backed writes
- do not add broad new integration scaffolding

## Residuals To Keep Explicit

- `install_from_snapshot()` still materializes filesystem layout
- marketplace lineage still lives in `meta.json.source`
- snapshot-driven local skill/agent/rule files remain local artifacts for now

## Stopline

Do not:

- reshape outward member payloads
- add new fallback from repo failure into filesystem writes
- merge marketplace lineage replacement into this seam
- delete snapshot/install filesystem helpers just because normal writes stop using them
