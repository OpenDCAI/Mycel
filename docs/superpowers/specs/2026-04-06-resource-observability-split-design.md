# Resource Observability Split Design

**Goal:** Keep `monitor` as the global ops/admin resource surface while moving product resources onto a user-scoped contract, without letting product code depend on monitor contracts.

## Constraints

- `monitor` depends on infrastructure and domain facts, not product services.
- Product resources must not depend on `/api/monitor/resources`.
- Preserve the current repo/protocol abstraction style.
- Do not add new SQLite implementations in this workstream.
- User direction is stricter than issue `#205`: old monitor/resource backend should also move to Supabase.
- Frontend changes should stay minimal and mostly reuse existing resource rendering.

## Current Facts

### Stable facts

- `PR #182` establishes `monitor` as a global runtime/ops surface.
- Issue `#205` explicitly says `/api/monitor/resources` should remain a global/admin overview and product resources should move to a dedicated user-scoped API.
- `storage/providers/supabase/sandbox_monitor_repo.py` already exists and covers most monitor read queries.

### Blocking facts

- `backend/web/core/storage_factory.py::make_sandbox_monitor_repo()` is still hardwired to SQLite.
- `storage/contracts.py` and `storage/container.py` do not model `SandboxMonitorRepo`.
- Sandbox write truth is still local-SQLite-centric:
  - `sandbox/manager.py` directly constructs `SQLiteTerminalRepo`, `SQLiteLeaseRepo`, `SQLiteChatSessionRepo`
  - `sandbox/chat_session.py` persists via `connect_sqlite`
  - `sandbox/terminal.py` persists terminal state via `connect_sqlite`
  - `sandbox/lease.py` persists lease state via `connect_sqlite`
  - `backend/web/utils/helpers.py`, `backend/web/routers/threads.py`, `backend/web/routers/webhooks.py` still directly hit SQLite sandbox repos

### Active branch facts

- Active continuation is `#210`, not `#209`.
- `#210` uses `PR #182` as the monitor baseline by transplanting the compat monitor onto a current resource-split branch instead of building on the reduced dev monitor shell.
- This branch keeps the full compat operator surface (`threads`, `traces`, `leases`, `evaluation`) and applies a bounded light-theme cleanup so operators are not dropped into a dark, overloaded console.

## Proposal Comparison

### Proposal A: Read-path-only split

- Add `/api/resources/*`
- Keep `/api/monitor/resources`
- Move monitor reads to Supabase

Why it loses:
- It is dishonest under the stronger constraint.
- Read Supabase + write SQLite means two truth sources.
- The repo would still be producing sandbox truth locally while pretending monitor/resource migrated.

### Proposal B: Single new raw fact service

- Introduce a neutral raw fact owner
- Feed monitor and product projections from that shared source

What survives:
- One raw truth source feeding two projections is the right shape.
- DTO separation between monitor and product is required.

What changes:
- The real seam is lower than a service split. The truth source is still embedded in sandbox domain/storage code.

### Proposal C: Final chosen direction

- Keep `/api/monitor/resources` as the global/admin monitor contract.
- Add `/api/resources/*` as the user-visible contract for product resources.
- Move `SandboxMonitorRepo` into `storage/contracts.py` and `storage/container.py`.
- Keep `resource_service.py` only as an application-level aggregator, not the owner of raw storage truth.
- Treat sandbox lease/terminal/chat_session persistence as the real migration seam.

## Architecture

### Layering

- Infra/domain truth:
  - storage repos
  - sandbox lease/terminal/chat-session persistence
  - resource snapshots / telemetry
- Shared resource helpers:
  - provider catalog / console URL / capability lookup
  - telemetry normalization and metric shaping
  - runtime thread/member owner lookup
- Global monitor projection:
  - monitor routes and services
  - global/admin DTOs
- Product resource projection:
  - `resource_projection_service.py`
  - resource routes and services
  - user-visible DTOs

### Dependency rules

- Product may not import monitor-layer contracts or services.
- Monitor may not import product-layer services.
- Both may depend on shared storage/domain truth.
- Shared truth enters through storage contracts, not ad-hoc SQLite factories.
- Shared projection helpers should live in a neutral helper module, not as private imports back into `resource_service.py`.

## Honest Scope Boundary

If we truly enforce "old monitor/resource backend also moves to Supabase", this is not a narrow issue-`#205` API refactor. It becomes a broader sandbox storage migration because domain objects and managers still persist directly to SQLite.

That means there are only two honest choices:

1. Widen the implementation to include the sandbox truth-source seam.
2. Narrow the claim and stop saying the old monitor/resource backend is Supabase-only.

This design chooses option 1 in architecture, but decomposes the implementation into cuts so the work stays reviewable.

## Implementation Cuts

### Cut A: Sandbox truth-source rewiring

- Make lease/terminal/chat-session repo construction strategy-aware instead of directly constructing SQLite repos.
- Remove monitor/resource-path assumptions that local SQLite is always the truth source.
- This cut exists to make Supabase a possible truth source rather than a read-only mirror.

### Cut B: Observability contract split

- Add `SandboxMonitorRepo` to the main storage abstraction.
- Keep `/api/monitor/resources` global.
- Add `/api/resources/*` for user-visible resources.
- Rewire product resource callers to the new contract.

## Non-goals

- Large frontend redesign.
- New product controls that paper over backend seams.
- Pretending the current SQLite-backed sandbox domain objects are already storage-agnostic.

## Verification Shape

- Backend proof that global monitor resources still work.
- Backend proof that user-scoped resources no longer read `/api/monitor/resources`.
- Explicit proof of where truth is written under Supabase mode.
- Playwright CLI proof for the compat monitor shell itself after the `PR #182` transplant:
  - page paths: monitor `/threads`, `/evaluation`, `/evaluation?new=1`, `/leases?diverged=1`
  - visible proof: light-theme shell, focused top nav (`Threads / Traces / Leases / Eval`), usable evaluation config modal, and preserved rich operator flows
  - trace proof: `/api/monitor/threads`, `/api/monitor/evaluations`, and `/api/monitor/leases` still answer on the transplanted branch
- Playwright CLI proof for the product resources surface after the API split:
  - page path: app `/resources`
  - visible proof: resources header, active/session counters, refresh button, at least one provider card
  - trace proof: browser requests include `/api/resources/overview` and exclude `/api/monitor/resources`
- Playwright CLI proof for the global monitor surface so the global contract is not accidentally broken while fixing the product page:
  - page path: monitor `/leases`
  - visible proof: monitor shell/logo plus leases table headers
  - trace proof: browser requests include `/api/monitor/leases` and exclude `/api/resources/*`
- Small frontend testability improvements are allowed when they are selector-only changes, especially `data-testid` markers on product resource page elements and provider cards.
