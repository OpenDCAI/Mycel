# Entities Avatar Auth Shell Design

**Date:** 2026-04-07
**Branch:** `code-killer-phase-5`

## Goal

Tighten the ownership/auth shell around avatar upload/delete routes without changing avatar processing behavior.

## Scope

This seam is limited to:

- `backend/web/routers/entities.py`
- focused tests for avatar auth/404/403 behavior

This seam explicitly does **not** cover:

- avatar image processing or resizing rules
- public avatar reads
- entity list/profile/agent-thread behavior
- auth service avatar bootstrap logic
- monitor/resource or panel/task contracts

## Problem

`entities.py` repeats the same member authorization shell across two avatar mutation routes:

1. fetch member from `member_repo.get_by_id(member_id)`
2. raise `404` when missing
3. allow only the member themselves or the owning user
4. raise `403` otherwise

That duplication is small but real. It creates two risks:

- upload/delete auth semantics can drift because each route owns its own copy
- future cleanup around avatar routes has to read past repeated shell logic before reaching the route-specific file behavior

## Chosen Approach

Keep the auth shell inside `entities.py`, but make it single-owned.

Concretely:

- add one narrow helper that resolves an avatar target member and enforces the existing `404` / self-or-owner / `403` contract
- keep avatar file handling, content-type checks, size checks, and save/delete logic exactly where they are
- change upload/delete routes to call the helper instead of open-coding the same checks
- add focused tests that pin missing-member, wrong-user, and owner/self success behavior

This keeps the seam honest:

- no business logic moves into a service/repo layer
- no new generic auth abstraction is introduced
- route-specific avatar behavior stays explicit and local

## Alternatives Considered

### 1. Leave the duplication and only add tests

Rejected.

That adds proof but leaves the repeated shell scattered across both routes.

### 2. Push avatar auth checks into a shared service

Rejected.

That would widen the seam and mix HTTP authorization semantics with lower-layer behavior.

### 3. Recommended: one router-local helper for avatar target authorization

Accepted.

It is the smallest simplification that shortens the contract while preserving route-local behavior.

## Intended Code Shape

### Router-local avatar auth shell

`entities.py` should own a helper along the lines of:

- `_get_owned_avatar_member_or_404(member_id, current_user_id, member_repo)`

The helper should:

- fetch the member from the repo
- raise `HTTPException(404, "Member not found")` when absent
- allow when `member_id == current_user_id`
- allow when `member.owner_user_id == current_user_id`
- raise `HTTPException(403, "Not authorized")` otherwise
- return the member row unchanged on success

### Route behavior stays explicit

The routes should still keep their own local behavior:

- `upload_avatar()` still validates content type, emptiness, size, and image decoding
- `delete_avatar()` still checks file existence and clears the repo avatar field
- `get_avatar()` remains public and unchanged

## Testing Strategy

This seam only matters if behavior stays identical.

### Focused tests

Add focused tests that prove:

- the helper allows self-owned and owner-owned members
- the helper raises `404` for missing members
- the helper raises `403` for unrelated users
- `upload_avatar()` and `delete_avatar()` still route through the same auth shell

### Verification

Minimum branch proof:

- focused entities avatar auth pytest file
- existing panel/task/thread focused tests as branch sanity
- `python3 -m py_compile` on touched router/test files

## Stopline

This PR stops at entities avatar auth shell simplification.

It must **not** expand into:

- changing avatar processing or file formats
- changing public avatar serving
- changing entity/profile/thread route behavior
- moving auth checks into service/repo layers
