# Panel Member Auth Shell Design

**Date:** 2026-04-07
**Branch:** `code-killer-phase-4`

## Goal

Tighten the ownership/auth shell around panel member routes without changing member CRUD behavior.

## Scope

This seam is limited to:

- `backend/web/routers/panel.py`
- focused tests for panel member auth/404/403 behavior

This seam explicitly does **not** cover:

- task / cron owner contracts
- `member_service.py` storage semantics
- provider / runtime / monitor / resource contracts
- builtin Leon behavior beyond preserving existing guards
- frontend product changes

## Problem

`panel.py` repeats the same member ownership shell across multiple routes:

1. fetch member via `member_service.get_member(member_id)`
2. raise `404` when missing
3. raise `403` when `owner_user_id` mismatches
4. continue with route-specific service call

That duplication is small but real. It creates two risks:

- panel member routes can drift on auth/404 semantics because each one owns its own shell
- future panel cleanup gets noisier because the router mixes route intent with repeated ownership gates

## Chosen Approach

Keep the shell inside `panel.py`, but make it single-owned.

Concretely:

- add one narrow helper that resolves a panel member and enforces the existing `404` / `403` contract
- keep builtin guard clauses (`__leon__` publish/delete restrictions) at the route level
- change member routes to call the helper instead of open-coding the same checks
- add focused tests that pin missing-member, wrong-owner, and injected-repo behavior

This keeps the seam honest:

- no business rules move into `member_service.py`
- no new router abstraction beyond the existing repeated shell
- route-specific behavior stays local and visible

## Alternatives Considered

### 1. Leave the duplication and only add tests

Rejected.

That improves proof but keeps the repeated auth shell scattered across each route.

### 2. Push owner checks into `member_service.py`

Rejected.

That would mix HTTP auth semantics with service/storage logic and widen the seam unnecessarily.

### 3. Recommended: one router-local helper for member ownership checks

Accepted.

It is the smallest simplification that shortens the contract without hiding route-specific behavior.

## Intended Code Shape

### Router-local auth shell

`panel.py` should own a helper along the lines of:

- `_get_owned_member_or_404(member_id, user_id)`

The helper should:

- call `member_service.get_member(member_id)`
- raise `HTTPException(404, "Member not found")` when absent
- raise `HTTPException(403, "Forbidden")` when owner mismatches
- return the member dict unchanged otherwise

### Route behavior stays explicit

Routes should still keep their own special cases:

- `publish_member()` continues to reject `__leon__` before touching the helper
- `delete_member()` continues to reject `__leon__` before touching the helper
- update/config/publish/delete still perform their own service calls after the helper returns

## Testing Strategy

This seam only matters if behavior stays identical.

### Focused tests

Add focused tests that prove:

- `list_members()` still uses the injected repo for owner-scoped listing
- helper-backed member routes still raise `404` for missing members
- helper-backed member routes still raise `403` for wrong-owner members
- builtin publish/delete guards still fire before any ownership helper path

### Verification

Minimum branch proof:

- focused panel auth pytest file
- existing panel task owner pytest file
- `python3 -m py_compile` on touched router/test files

## Stopline

This PR stops at panel member auth shell simplification.

It must **not** expand into:

- changing member CRUD storage behavior
- changing builtin Leon policy
- mixing in panel task / cron cleanup
- moving HTTP ownership logic into service/repo layers
