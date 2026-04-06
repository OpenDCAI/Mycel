# Entities Member Lookup Shell Design

## Goal

Remove the repeated public member lookup and `404 "Member not found"` shell in `backend/web/routers/entities.py` without changing any route-specific behavior.

## Scope

In scope:

- `GET /api/entities/{user_id}/profile`
- `GET /api/entities/{user_id}/agent-thread`

Out of scope:

- profile response shaping
- avatar routes
- auth or ownership checks
- the `No agent thread found` branch in `get_agent_thread`

## Existing Problem

Two nearby routes repeat the same opening shell:

1. `member = app.state.member_repo.get_by_id(user_id)`
2. if missing, raise `HTTPException(404, "Member not found")`

The duplication is mechanical, but the routes diverge immediately after that:

- `get_entity_profile` validates the member type and shapes a public profile response
- `get_agent_thread` asks `thread_repo` for the main thread and may still raise `404 "No agent thread found"`

So the simplification must stop after the shared member lookup and not flatten the later route-specific branches.

## Design

Keep the change router-local inside `backend/web/routers/entities.py`.

Add one helper:

- `_get_member_or_404(app, user_id)`

That helper does exactly two things:

- call `member_repo.get_by_id(user_id)`
- raise `404 "Member not found"` when absent

Both routes reuse the helper and keep their existing downstream logic unchanged.

## Testing

Extend `tests/Integration/test_entities_router.py` with focused tests that pin:

- helper returns the member when found
- helper raises `404` when missing
- `get_entity_profile` delegates through the helper
- `get_agent_thread` delegates through the helper

The route tests should only prove delegation and preserve the existing route-specific branches. They must not rewrite the later `Profile not available for this member type` or `No agent thread found` behavior.

## Stopline

Do not:

- move the helper into another module
- touch profile shaping
- touch `get_agent_thread` thread lookup semantics
- touch avatar routes
- add auth or ownership logic
