# Evaluation Monitor Surface Design

## Goal

Restore a real monitor-facing evaluation page that consumes the truthful backend surface added in `PR-D1/#264`, without pretending that evaluation runtime activation is already finished.

## Current Facts

- `GET /api/monitor/evaluation` now exists and returns operator truth.
- Current truth is still explicitly `status=unavailable` until a real runtime source is wired.
- The revived monitor shell already exists and mounts these routes:
  - `/dashboard`
  - `/threads`
  - `/resources`
  - `/leases`
  - `/diverged`
  - `/events`
- There is no mounted monitor evaluation page yet.
- Dashboard currently derives evaluation summary, but it is still only a summary, not a real operator surface.

## Approaches

### 1. Dashboard-only evaluation exposure

Keep evaluation visible only as a dashboard summary card.

- Smallest diff
- Keeps dashboard overloaded
- Does not give operators a dedicated place to inspect evaluation facts, artifacts, and next steps

Not recommended.

### 2. Dedicated evaluation page

Add a real `/evaluation` route and sidebar entry that consumes `/api/monitor/evaluation`.

- Matches the shell revival direction
- Uses the truth route that already exists
- Keeps `PR-D2` narrow: mounted monitor surface only
- Cleanly separates `PR-D2` from `PR-D3`

Recommended.

### 3. Full evaluation comeback

Add page, nav, traces, drilldown, and runtime activation all at once.

- Recreates the old “one giant PR” failure mode
- Mixes frontend surface work with runtime/operator semantics

Rejected.

## Recommended Design

`PR-D2` will add a dedicated monitor evaluation surface:

- new route: `/evaluation`
- new sidebar entry: `Evaluation`
- new page component that fetches `/api/monitor/evaluation`
- page sections that map directly to the current operator payload:
  - headline/status section
  - fact list
  - artifact summary + artifact table
  - next steps
  - raw notes block when present

This page must remain honest when the runtime source is not yet wired. If the payload says `status=unavailable`, the page should render that operator truth directly instead of inventing zero-state metrics or fake healthy copy.

## Architecture

### Route and navigation

- Extend `frontend/monitor/src/app/routes.tsx` with `/evaluation`
- Extend `frontend/monitor/src/app/monitor-nav.ts` with an `Evaluation` entry
- Do not change existing mounted routes

### Page component

Add `frontend/monitor/src/pages/EvaluationPage.tsx`.

Responsibilities:

- fetch `/evaluation` using existing `useMonitorData`
- render `ErrorState` on request failure
- render loading state while fetch is pending
- render truthful operator sections once payload exists

The page should follow the same shell/page grammar already used by `DashboardPage`, `LeasesPage`, and `EventsPage`.

### Data mapping

No backend payload changes are part of `PR-D2`.

The page should consume these existing fields directly:

- `status`
- `kind`
- `tone`
- `headline`
- `summary`
- `facts`
- `artifacts`
- `artifact_summary`
- `next_steps`
- `raw_notes`

If a field is absent, the page may render a minimal fallback label like `-`, but it must not invent a different semantic state.

## UI Structure

### Hero section

- page title: `Evaluation`
- subtitle/description taken from `headline` and `summary`
- compact status chip showing `status` and `kind`

### Operator surface cards

Small cards derived from `artifact_summary`:

- present artifacts
- missing artifacts
- total artifacts

If `status=running`, the page may visually emphasize operator activity, but this should come from existing payload truth, not client-side inference beyond the status field.

### Facts section

Render the `facts` array as a simple key/value grid.

### Artifacts section

Render the `artifacts` array as a table:

- label
- path
- status

### Next steps section

Render `next_steps` as a flat ordered list. These are already operator-oriented instructions; no additional UI inference is needed.

### Raw notes section

Render only when `raw_notes` is non-null. Use a monospace block and keep it visually secondary.

## Error Handling

- Request failure: use existing `ErrorState`
- `status=unavailable`: render as valid page content, not as an error
- Empty arrays: render honest empty sections, not placeholder business claims

## Testing

`PR-D2` should be locked with frontend route smoke only.

Minimum verification:

- `src/app/routes.test.tsx`
  - sidebar contains `Evaluation`
  - `/evaluation` route mounts and highlights nav correctly
  - unavailable payload renders truthful operator copy
- `npm run build`

No backend contract tests belong in this PR unless the frontend reveals a real contract gap.

## Boundaries

### In scope

- monitor sidebar entry
- monitor evaluation page
- truthful rendering of the existing `/api/monitor/evaluation` payload

### Out of scope

- evaluation runtime activation
- traces drilldown
- dashboard semantic rewrite
- product-facing evaluation UI
- backend payload expansion

## Merge Bar

- `/evaluation` exists inside the revived monitor shell
- sidebar navigation reaches it
- page truthfully renders the current unavailable payload
- route smoke passes
- monitor frontend build passes
- no backend contract changes are required for this slice
