# Thread Launch Config Contract Design

**Date:** 2026-04-06
**Branch:** `code-killer-phase-3`

## Goal

Tighten and simplify the launch-config contract that drives thread defaults and persisted "last confirmed / last successful" state.

## Scope

This seam is limited to:

- `backend/web/services/thread_launch_config_service.py`
- `backend/web/routers/threads.py`
- focused tests that cover launch-config save/build behavior

This seam explicitly does **not** cover:

- display/history/SSE
- monitor/resource contracts
- runtime/provider/checkpointer/lifespan
- panel/task wiring
- broader thread-create behavior changes

## Problem

The launch-config contract is semantically one thing, but it currently lives in three loosely coupled shapes:

1. `save_default_thread_config()` posts a payload and persists it through `save_last_confirmed_config()`
2. `create_thread()` hand-builds a `successful_config` dict in two branches
3. `resolve_default_config()` later validates and derives defaults against the same shape

That creates two risks:

- launch-config shape is easy to drift because the router still hand-builds the "successful" dict
- the service that owns normalization/validation has almost no direct tests, so the product path depends on shape conventions more than explicit proof

## Chosen Approach

Use `thread_launch_config_service.py` as the single contract owner for persisted launch-config payloads.

Concretely:

- keep `normalize_launch_config_payload()` as the canonical persisted shape
- add narrow builder helpers for:
  - successful config from an existing lease
  - successful config from a new sandbox launch
- deduplicate the two save functions behind one tiny internal save helper
- change `threads.py` to ask the service for the successful-config payload instead of hand-building it inline

This keeps the seam honest:

- the router stops owning launch-config shape
- the service owns both normalization and successful-payload construction
- no generic abstraction is introduced

## Alternatives Considered

### 1. Leave router dicts as-is and only add tests

Rejected.

That improves proof but leaves the contract duplicated across router and service.

### 2. Introduce a generic launch-config object/class

Rejected.

This is too much machinery for a narrow shape-normalization seam.

### 3. Recommended: explicit builder helpers inside the service

Accepted.

It is the smallest change that shortens the contract boundary without hiding semantics.

## Intended Code Shape

### Service layer owns the launch-config shape

`thread_launch_config_service.py` should expose:

- `normalize_launch_config_payload(payload)`
- `build_existing_launch_config(...)`
- `build_new_launch_config(...)`
- `save_last_confirmed_config(...)`
- `save_last_successful_config(...)`
- `resolve_default_config(...)`

The save functions remain thin, but no longer duplicate the repo write shape internally.

### Router stops hand-building successful payloads

`threads.py` should call the service helpers:

- existing lease branch → `build_existing_launch_config(...)`
- new thread branch → `build_new_launch_config(...)`

The router still chooses which branch applies. The service owns the resulting payload shape.

## Testing Strategy

This seam needs direct proof because the current repo barely tests it.

### Focused tests

Add a new focused test file that proves:

- `save_last_confirmed_config()` persists normalized shape
- `build_existing_launch_config()` and `build_new_launch_config()` produce canonical payloads
- `create_thread()` persists the same canonical successful payload shape for:
  - reused existing lease
  - new sandbox launch

### Verification

Minimum branch proof:

- focused launch-config pytest file
- existing `tests/Integration/test_threads_router.py`
- `frontend/app npm run build`
- `python3 -m py_compile` on touched backend files

## Stopline

This PR stops at launch-config contract ownership and proof.

It must **not** expand into:

- changing thread-create business rules
- redesigning default-config product behavior
- threading new settings/workspace semantics through the whole app
- resource/monitor cleanup
