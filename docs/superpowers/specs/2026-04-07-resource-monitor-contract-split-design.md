# Resource / Monitor Contract Split Design

**Date:** 2026-04-07
**Branch:** `dev`

## Goal

Split the global monitor resource contract from the future user-visible resources contract without changing the current product intent:

- monitor keeps a global/system overview
- user-facing resources get a dedicated backend contract
- non-sandbox storage stays Supabase-only
- no fallback back to SQLite for this slice

## Scope

This design covers:

- `backend/web/services/resource_service.py`
- `backend/web/services/resource_cache.py`
- `backend/web/services/sandbox_service.py`
- `backend/web/routers/monitor.py`
- one new backend router/service pair for user-scoped resources
- focused backend tests for the new contract

This design explicitly does **not** cover:

- monitor UI redesign
- runtime / streaming / checkpointer / provider changes
- thread launch config contract work
- re-enabling a `/resources` frontend route on the current tree
- broad monitor/resource dedupe work beyond the new user contract

## Current Facts

The current tree has two different truths mixed together.

### 1. Global monitor overview already exists

`resource_cache -> resource_service.list_resource_providers()` builds a cached provider/session snapshot for `/api/monitor/resources`.

That path is monitor-shaped:

- provider-oriented snapshot
- global session aggregation
- background refresh loop
- fallback projection of raw monitor rows into a stable overview

This is still useful and should stay intact for ops/admin/debugging.

### 2. User-visible lease truth also already exists

`sandbox_service.list_user_leases(owner_user_id, ...)` already knows which leases are visible to the current signed-in user.

That path is product-shaped:

- owner-scoped
- filters out internal child/virtual thread identities
- returns only visible lease bindings

This is the right ownership/visibility source for a future user resources page.

### 3. The frontend situation has changed since issue #205 was written

On the current tree, `/resources` is no longer an active product route.

`frontend/app/src/router.tsx` redirects `/resources` to `/marketplace`, and `frontend/app/src/pages/resources/*` appears to be residual helper/components rather than a live route.

That means issue #205 is still a real backend contract problem, but not a live frontend regression on the current tree.

## Problem

Right now the codebase still implies that one resource surface can serve both purposes:

- monitor wants full topology
- product wants only owner-visible resources

Those are different contracts.

If we keep forcing both through `/api/monitor/resources`, we get one of two bad outcomes:

1. monitor gets watered down to satisfy product needs
2. product inherits global fallback rows, stale monitor semantics, and system-shaped payload choices

Neither is acceptable.

## Chosen Approach

Create a narrow user-scoped projection service and a new backend endpoint:

- keep `/api/monitor/resources` as-is for global monitor overview
- add `GET /api/resources/overview` for user-scoped resource projection
- build the user projection from `sandbox_service.list_user_leases(...)` plus reused provider/session shaping helpers from `resource_service.py`

This is the smallest honest split because it:

- preserves existing monitor behavior
- reuses existing ownership truth instead of inventing a new source
- keeps future frontend migration cheap by returning a payload close to the current `ResourceOverviewResponse`

## Alternatives Considered

### 1. Frontend-only URL swap

Rejected.

Changing the frontend to call a different endpoint is not enough unless the backend first defines a different contract. Otherwise the projection logic simply moves around without becoming clearer.

### 2. Full monitor/resource re-architecture now

Rejected for now.

The current tree does not even expose a live `/resources` route, so a full rewrite would be architecture-first work with low immediate product payoff.

### 3. Recommended: add a user projection beside monitor

Accepted.

This keeps boundaries explicit while minimizing churn.

## Intended Backend Shape

### Monitor path stays global

Keep:

- `resource_cache.py` as the monitor snapshot cache
- `resource_service.list_resource_providers()` as the global provider/session aggregation entrypoint
- `/api/monitor/resources` and `/api/monitor/resources/refresh`

The monitor path should continue to reflect system/resource topology, not user-product filtering.

### New user projection path

Add a small backend service, for example:

- `backend/web/services/resource_projection_service.py`

Its job is:

- accept `owner_user_id`
- call `sandbox_service.list_user_leases(...)`
- derive the visible provider/session groups for that owner
- reuse capability/catalog/telemetry shaping from `resource_service.py` where honest
- return a payload compatible with the existing resource card/session types where practical

This service should not depend on monitor cache.

### Shared helper extraction

Some logic in `resource_service.py` is monitor-specific and some is reusable.

The reusable part includes:

- provider catalog metadata
- provider capability resolution
- metric shaping helpers
- session metric normalization

The monitor-specific part includes:

- cached snapshot semantics
- global raw session query + projection
- drift detection against live sessions

The split should make that distinction clearer instead of duplicating the helpers blindly.

## API Design

### Existing monitor API

Keep unchanged:

- `GET /api/monitor/resources`
- `POST /api/monitor/resources/refresh`

### New user API

Add:

- `GET /api/resources/overview`

Response target:

- stay close to the current `frontend/app/src/pages/resources/api.ts` `ResourceOverviewResponse`
- especially preserve `summary` + `providers[]` + `sessions[]` card contract where possible

That keeps a future frontend migration low-risk: switching a route later should mostly mean changing the fetch URL, not rebuilding all card types.

## Error Handling

- If the user is unauthenticated, keep normal auth dependency behavior.
- If ownership-dependent repos are missing from app state, fail loudly with `500`; do not silently fall back to monitor/global data.
- If a provider cannot be initialized, user projection should surface provider unavailability honestly in the same spirit as monitor, but only for providers relevant to the user-visible result.

## Testing Strategy

Keep tests backend-focused and narrow.

### Required proof

- focused service/route tests for `GET /api/resources/overview`
- proof that the endpoint only returns owner-visible leases/sessions
- proof that monitor endpoints remain unchanged
- proof that cache invalidation behavior stays monitor-only

### Non-goals for this slice

- frontend route resurrection
- Playwright coverage for `/resources`
- monitor UI refactor

## Stopline

This slice stops when:

- monitor and user resource contracts are separate at the backend
- monitor remains global
- the future user contract exists and is tested
- the response shape is stable enough for a later frontend switch

It must **not** expand into:

- live resource page resurrection
- monitor redesign
- provider/runtime refactors
- resource/monitor grand dedupe program
