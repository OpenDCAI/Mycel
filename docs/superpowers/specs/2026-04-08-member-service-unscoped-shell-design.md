# Member Service Unscoped Filesystem Shellectomy

## Goal

Remove the remaining unscoped filesystem read shell from `backend/web/services/member_service.py` without changing outward member payload shape and without mixing marketplace lineage work into the same cut.

## Current Facts

Owner-scoped member reads are already repo-rooted:

- `list_members(owner_user_id=..., user_repo=..., agent_config_repo=...)`
- `get_member(member_id, user_repo=..., agent_config_repo=...)`

Those paths already resolve agent users from `user_repo` and config from `agent_config_repo`.

The remaining legacy shell is unscoped read behavior:

- builtin Leon still lives as a special-case local shell (`__leon__`)
- historical filesystem assumptions still shape the module structure and some branch behavior

This seam is now smaller than it used to be, but still worth freezing because the service still frames itself as `~/.leon/members` rooted and still mixes builtin/local shell concerns with repo-rooted reads.

## In Scope

- Unscoped member read behavior in `member_service`
- Clarify and isolate builtin `__leon__` read semantics
- Remove any remaining implication that generic unscoped member reads should walk `MEMBERS_DIR`
- Tighten tests around repo-rooted unscoped reads vs builtin-only behavior

## Out Of Scope

- Marketplace lineage / publish / install source replacement
- Member write/update filesystem removal
- New outward member payload shape
- New backward-compat fallback paths
- Any change to owner-scoped read contract already landed

## Approaches Considered

### A. Tiny cleanup only

Only rewrite comments/docstrings so they stop describing the service as filesystem-rooted.

Rejected:
- too weak
- does not enforce anything
- leaves the read contract ambiguous

### B. Recommended: unscoped read shell cut

Make the read contract explicit:

- `list_members()` unscoped returns builtin-only surface
- generic agent member reads require repo inputs
- `get_member("__leon__")` stays builtin-only and local
- no unscoped generic member read may silently fall back to `MEMBERS_DIR`

Why this is the right cut:
- bigger than cosmetic cleanup
- still local to `member_service`
- avoids mixing marketplace lineage or outward contract redesign

### C. Merge with marketplace/member write cleanup

Rejected:
- turns one readable seam into 2-3 contracts at once
- too easy to collide with the marketplace slice on `#259`

## Target Contract

1. Generic agent member reads are repo-rooted, not `MEMBERS_DIR` rooted.
2. Unscoped reads do not silently sweep filesystem member directories.
3. Builtin `__leon__` remains a special local read surface for now.
4. The outward payload shape of `list_members()` and `get_member()` does not change.
5. Fail loudly when a generic agent member read lacks the repo inputs needed to resolve it.

## Design

### 1. Split “builtin local shell” from “generic member read”

Keep `_leon_builtin()` as the only local unscoped read island.

Do not let that local builtin exception justify broader filesystem member discovery.

### 2. Make unscoped list behavior explicit

`list_members(owner_user_id=None, ...)` should remain builtin-only.

That behavior already exists in this branch, but the spec freezes it as the canonical unscoped read contract so it cannot drift back toward directory scanning.

### 3. Keep generic get-by-id repo-rooted

`get_member(member_id, user_repo=..., agent_config_repo=...)` remains the only path for agent member reads.

For non-builtin members:
- missing repos should raise loudly
- missing user row returns `None`
- missing `agent_config_id` or missing config row should remain loud contract failures

### 4. Do not mix write-shell cleanup into this seam

`update_member`, `update_member_config`, delete, import/install flows still contain filesystem branches.

Those are real residuals, but they are not part of this cut. This spec is only about read-side shell cleanup and contract clarity.

## Proof Plan

### Structure proof

- `member_service` read-side docs/comments no longer describe generic member reads as filesystem-rooted
- unscoped read branches are visibly limited to builtin-only behavior

### Fixture proof

- owner-scoped cutover tests stay green
- add or tighten tests that prove:
  - unscoped `list_members()` returns builtin-only surface
  - non-builtin `get_member()` requires repo inputs
  - builtin `__leon__` still resolves without repo inputs

### Runtime proof

For this seam, runtime proof is bounded:
- backend service callers can only get non-builtin member data through repo-backed reads
- no generic unscoped filesystem sweep remains on the read path

## Residuals To Keep Explicit

- `member_service` write/update paths still contain filesystem branches
- `marketplace_client` still has local member bundle behavior
- `config.loader` local bundle discovery still exists for explicit local/CLI workflows

## Stopline

Do not:

- redesign outward member payloads
- add fallback to filesystem reads
- fold marketplace lineage into this cut
- use this seam as an excuse to rewrite `member_service` wholesale
