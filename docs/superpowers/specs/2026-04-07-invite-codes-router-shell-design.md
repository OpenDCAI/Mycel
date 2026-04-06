# Invite Codes Router Shell Design

## Goal

Remove the repeated router-local repo-call and error-mapping shell in `backend/web/routers/invite_codes.py` without changing any invite-code contract.

## Scope

In scope:

- `GET /api/invite-codes`
- `POST /api/invite-codes`
- `DELETE /api/invite-codes/{code}`
- `GET /api/invite-codes/validate/{code}`

Out of scope:

- invite-code repo implementation
- auth requirements for each route
- the Chinese user-facing error prefixes

## Existing Problem

All four routes repeat the same shell:

1. `_get_invite_code_repo(request.app)`
2. `await asyncio.to_thread(...)`
3. `except HTTPException: raise`
4. `except Exception as e: raise HTTPException(500, f\"<route-specific-prefix>{e}\")`

That is a clean router-local seam. The routes still have their own semantics:

- `list` returns `{\"codes\": ...}`
- `generate` passes `created_by` and `expires_days`
- `revoke` must still translate a falsey repo result into `404 \"邀请码不存在\"`
- `validate` stays unauthenticated and returns `{\"valid\": ...}`

## Design

Keep the change inside `backend/web/routers/invite_codes.py`.

Add one helper:

```python
async def _call_invite_code_repo(
    request: Request,
    error_prefix: str,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    ...
```

The helper must:

- fetch the repo through `_get_invite_code_repo(request.app)`
- call the repo method with `asyncio.to_thread`
- preserve any `HTTPException` unchanged
- map any other exception to `HTTPException(500, f"{error_prefix}{error}")`

Each route stays responsible for its own semantics:

- each route passes its own Chinese `500` prefix explicitly
- `revoke` still handles `False` with `404 "邀请码不存在"` after the helper returns

## Testing

Add focused tests in `tests/Integration/test_invite_codes_router.py` that pin:

- helper returns the repo result on success
- helper maps generic exceptions to the provided Chinese `500` prefix
- helper preserves `HTTPException`
- `list_invite_codes` delegates through the helper with the list prefix
- `revoke_invite_code` delegates through the helper and still raises `404` when the helper returns `False`

Those tests must stay on the router shell. They must not drift into repo internals.

## Stopline

Do not:

- flatten the Chinese `500` prefixes into one shared message
- move `404 "邀请码不存在"` into the helper
- change auth requirements
- move the helper out of `invite_codes.py`
