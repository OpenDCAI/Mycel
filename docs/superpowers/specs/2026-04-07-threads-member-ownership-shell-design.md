# Threads Member Ownership Shell Design

## Goal

Remove the repeated member lookup and ownership gate in `backend/web/routers/threads.py` for the small launch-config surface without changing any business rule.

## Scope

In scope:

- `POST /api/threads/main`
- `GET /api/threads/default-config`
- `POST /api/threads/default-config`

Out of scope:

- `create_thread`
- launch-config persistence or precedence logic
- provider gate and mount gate behavior
- any thread runtime, streaming, or sandbox contract

## Existing Problem

`threads.py` currently repeats the same `member_repo.get_by_id(...)` plus owner check in three nearby routes. The duplication is small, but the file is sensitive enough that leaving repeated auth shell code invites drift.

The catch is that the three routes do not share the same failure contract:

- `resolve_main_thread` returns `{"thread": None}` when the member is missing or foreign
- `get_default_thread_config` and `save_default_thread_config` raise `403 "Not authorized"` when the member is missing or foreign

So the simplification must not flatten those two behaviors into one helper result.

## Design

Keep the seam router-local inside `backend/web/routers/threads.py`.

Add two tiny helpers:

1. A lookup helper that returns the owned member or `None`
2. A strict helper that reuses the lookup helper and raises `403 "Not authorized"` when the owned member is absent

This keeps the repeated repo lookup and owner check in one place while preserving the two route contracts:

- `/main` keeps the soft-null behavior
- `/default-config` keeps the strict 403 behavior

## Testing

Add focused tests in `tests/Fix/test_thread_launch_config_contract.py` that pin:

- the soft helper returns `None` for a foreign member
- the strict helper raises `403`
- `resolve_main_thread` uses the soft helper contract
- `GET /default-config` uses the strict helper contract
- `POST /default-config` uses the strict helper contract

The tests must not assert or rewrite launch-config precedence, existing/new thread creation, or provider-gate behavior.

## Stopline

Do not:

- move this logic into a service or repo
- touch `thread_launch_config_service.py`
- change `resolve_main_thread` null semantics
- change `default-config` 403 semantics
- touch `create_thread` or any provider gate code
