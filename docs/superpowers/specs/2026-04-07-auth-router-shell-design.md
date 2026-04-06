# Auth Router Shell Design

## Goal

Remove the repeated router-local service-call and `ValueError` to `HTTPException` mapping in `backend/web/routers/auth.py` without changing any auth contract.

## Scope

In scope:

- `POST /api/auth/send-otp`
- `POST /api/auth/verify-otp`
- `POST /api/auth/complete-register`
- `POST /api/auth/login`

Out of scope:

- auth service implementation
- token generation or verification
- frontend auth flow
- chat event auth in `messaging.py`

## Existing Problem

`auth.py` repeats the same shape four times:

1. call a method on `_get_auth_service(app)` through `asyncio.to_thread`
2. map `ValueError` into `HTTPException`

The seam is clean, but the routes do not all share the same HTTP contract:

- the three registration steps map `ValueError` to `400`
- `login` maps `ValueError` to `401`

So the simplification must preserve the route-specific status code instead of flattening everything into one error mapping.

## Design

Keep the change router-local inside `backend/web/routers/auth.py`.

Add one helper that:

- accepts the app
- accepts the route-specific status code
- accepts the auth service method name and call args
- executes the call through `asyncio.to_thread`
- maps `ValueError` into `HTTPException(status_code, str(error))`

Each route stays responsible for its own status code:

- registration routes pass `400`
- login passes `401`

This keeps the contract explicit while removing the repeated shell.

## Testing

Extend `tests/Integration/test_auth_router.py` with focused tests that pin:

- helper returns the service result when the call succeeds
- helper maps `ValueError` to the provided status code
- `send_otp` delegates through the helper with `400`
- `login` delegates through the helper with `401`

Those tests must not drift into auth service behavior. They only verify the router shell contract.

## Stopline

Do not:

- move the helper into a shared utility module
- change auth service methods
- change route payloads or response bodies
- change login from `401` to `400`
- touch `messaging.py` even though the test file also covers chat auth
