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
- Latest frontend review closeout on `#210` is intentionally narrow: `EvaluationDetailPage` now gives the primary status chip semantic warning/danger/success treatment instead of leaving status visually flatter than the secondary publishable chip, and the score-grid JSX structure was re-indented so future edits do not misread the DOM hierarchy.

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

## Newly Surfaced Defects And Follow-up Slices

These are not vague “polish later” notes. They are concrete seams that now block an honest first merge of the monitor base.

### Slice D1: Threads Pagination Honesty

- Current defect:
  - `/api/monitor/threads?offset=50&limit=50` returns `items=[]` while still reporting `total=74`, `page=2`, and `has_next=true`.
  - The page therefore shows impossible copy like `Showing 51-50 of 74`.
- Root cause:
  - `backend/web/monitor.py::list_threads()` paginates once in SQL, appends checkpoint-only evaluation threads, then slices again with `items[offset:offset+limit]`.
- Required outcome:
  - single pagination semantic
  - truthful `has_next/next_offset`
  - no inverted count labels

### Slice D2: Evaluation Provisional Operator Surface

- Current defect:
  - real provisional eval detail technically renders, but operator-facing meaning is weak enough that the page reads like “nothing is there”.
- Required outcome:
  - provisional state must explain what exists now, what is still pending, where logs/artifacts live, and what the operator should do next.
  - this is a backend-first surface; if new fields are needed, add them to the payload instead of making the frontend guess from free-text notes.
- Current landed phase:
  - evaluation detail payload now includes `info.operator_surface`, built by a database-agnostic helper in `backend/web/services/monitor_service.py`
  - the monitor eval detail page now opens with a dedicated `Operator Status` block instead of leading with a sparse provisional score grid
  - the first screen now explains `runner exit before threads materialized`, surfaces `run_dir / manifest / stdout / stderr`, and gives explicit next-step guidance
  - redundant provisional score metadata is still available, but collapsed behind `Score artifacts (provisional)` by default so the page reads like an operator surface instead of a failed report
  - operator payload now also carries a typed `kind` plus `artifact_summary`, and keeps all six artifact slots (`run_dir / manifest / stdout / stderr / eval_summary / trace_summaries`) with explicit `present|missing` status instead of filtering missing ones away
  - the same backend helper now distinguishes at least `bootstrap_failure`, `running_waiting_for_threads`, `running_active`, `completed_with_errors`, `completed_publishable`, and `provisional_waiting_for_summary`
- Honest boundary:
  - this phase now covers the main eval lifecycle branches more honestly, but it is still a typed operator contract layered over compat-monitor facts rather than a deeper evaluation storage rewrite

### Slice D3: Lease Semantics And Regrouping

- Current defect:
  - `/leases` currently dumps raw orphan/diverged rows with minimal explanation.
  - operator cannot tell whether they are seeing stale history, expected cleanup lag, or a real infrastructure problem.
- Required outcome:
  - keep raw/global truth available
  - add explicit categorization/regrouping for active, diverged, orphan, and historical leases
  - reduce “system looks broken” confusion without hiding the raw facts
- Current landed phase:
  - `/api/monitor/leases` still preserves the original `summary/groups/items` contract, but now also returns backend-owned `triage.summary` and ordered `triage.groups`
  - the new `triage` layer separates `active_drift`, `detached_residue`, `orphan_cleanup`, and `healthy_capacity`
  - classification is still built from existing database-agnostic fields (`desired_state`, `observed_state`, `thread_id`, `updated_at`) rather than new SQLite-specific lookups
  - the monitor `Resources` page now reads that triage surface directly, so the live page can show `3 active drift + 26 detached residue` instead of one opaque `29 diverged`
  - the legacy `/leases` page now also uses the triage surface for its first screen, so direct operators no longer land on a single flat alarming table by default
- Honest boundary:
  - this is still a phase-2 heuristic, not a full lifecycle model; age-based detached residue is a better operator default, but not yet a richer typed runtime contract

### Slice D4: Dashboard Entry And Global Resources Surface

- Current defect:
  - monitor still drops operators straight into a list page
  - monitor has no first-class global resources surface even though `/api/monitor/resources` already exists
  - the current top-nav caption is redundant and should be removed
- Required outcome:
  - add a dashboard landing page
  - add a monitor resources entry, likely by transplanting/reusing the existing `ResourcesPage` visual structure against the global monitor contract
  - keep product `/resources` on the user-scoped contract and keep monitor resources global

## Current IA Direction

This is the current recommended monitor IA after the latest user review and the Chloe/CCM design pass.

### Top-level Navigation

- `Dashboard`
- `Threads`
- `Resources`
- `Eval`

### Explicit removals / merges

- remove the top-nav caption (`Global ops surface...`)
- stop defaulting `/` to `/threads`; default to `/dashboard`
- merge the current top-level `Traces` tab into the thread drill-down path instead of keeping it as a separate first-class nav destination
- replace the top-level `Leases` tab with `Resources`; lease health remains visible, but as one section inside the broader resources/infrastructure surface

### Dashboard Shape

- `Infra Health`
  - provider availability
  - diverged lease count
  - orphan lease count
  - links into filtered resource/lease views
- `Active Workload`
  - active threads
  - running sessions
  - recent errors
- `Eval Snapshot`
  - latest evaluation status
  - progress
  - publishable/final score when available

The dashboard is a switchboard, not a full destination page. It should answer “what needs attention?” and route the operator into the right deeper surface.

### Resources Surface

- top section: global provider cards and provider detail, transplanted from the existing product `ResourcesPage` family where possible
- bottom section: lease health triage, grouped instead of dumped
  - diverged
  - orphan
  - healthy/history (collapsed or de-emphasized)

### Current D4 Phase-1 Landing

- compat monitor now has a real `/dashboard` entry backed by `/api/monitor/dashboard`
- top-level nav is now `Dashboard / Threads / Resources / Eval`
- root route now lands on `/dashboard`
- top-nav caption has been removed
- monitor `Resources` is now a first-class page using the global monitor contract:
  - `GET /api/monitor/resources`
  - `POST /api/monitor/resources/refresh`
  - `GET /api/monitor/leases`
- the monitor resources page now has:
  - provider grid
  - selected provider detail
  - global session table per provider
  - grouped lease health sections (`Diverged`, `Orphans`, `All leases`)
- evaluation guidance is no longer sprayed across the first screen; tutorial/reference sections are now collapsed by default behind an operator-guide `<details>` block

### Current D4 Phase-2 Landing

- monitor provider cards are now much closer to the product `ResourcesPage` family:
  - status light in the title row
  - compact metric cells instead of plain text-only stats
  - capability strip
  - session status dot strip
  - unavailable providers still stay selectable in monitor so ops can inspect them, even though product cards disable that path
- selected provider detail is now a true panel instead of a loose stack:
  - provider header + status/type context
  - overview pill strip
  - capability strip reused in the detail pane
  - global session table kept below as the monitor-only truth surface
- monitor-side null telemetry now stays `--` instead of being accidentally coerced into `0.0`, which was misleading for unavailable providers

### Current D4 Phase-3 Landing

- selected provider detail now includes a monitor-side lease card grid above the raw session table
- this is the closest monitor equivalent to the product sandbox-card layer:
  - grouped by lease
  - surfaces member, thread, started time, and per-lease session counts
  - keeps the full raw session table below instead of replacing it
- the monitor page still does not import product frontend components directly; it mirrors the interaction shape locally so the contract boundary remains clean

### Current D4 Phase-4 Landing

- dashboard infra metrics now deep-link directly into monitor lease-health instead of stopping at the top of the resources page
- provider cards are tighter:
  - duplicated paused/stopped footer counts were removed
  - unavailable/error reason now lives in the header block instead of stretching card height
- lease-health now defaults to the non-empty attention buckets:
  - `active_drift` and `detached_residue` stay first-class
  - `orphan_cleanup` only renders when present
  - `healthy_capacity` is collapsed behind a details shell instead of competing with active failure buckets
- the net effect is not a new contract; it is a first-screen density cut so operators land on attention surfaces before passive inventory

### Current D4 Phase-5 Landing

- selected provider lease cards now drive a dedicated monitor-side `Lease Detail` panel before the global session truth table
- this is the smallest local equivalent of the product sandbox-sheet layer:
  - click a lease group card
  - inspect lease/thread quick links, member, started time, and per-session status rows
  - only then fall through to the noisier full provider session table
- the interaction stays frontend-local and contract-preserving:
  - no new backend fields
  - no import of product sandbox components
  - only existing provider/session/lease payload data is reused

### Current D4 Phase-6 Landing

- the provider session table now obeys the active drill-down instead of always dumping every provider row:
  - default scope is `Selected lease`
  - operator can explicitly switch to `All provider sessions`
- this turns the lease detail + session table into one coherent path:
  - choose lease
  - inspect lease detail
  - see only the session rows for that lease by default
  - opt back into the noisier provider-wide truth table when needed
- still no backend changes; this is a frontend-owned information-ordering fix over existing payload data

### D4 Remaining Gaps

- monitor provider/detail surface is now close to the product resources page in interaction quality, but still lacks the richer sandbox-sheet capabilities such as file browsing or per-session live metrics
- lease regrouping exists, but backend-side semantic categorization is still shallow and belongs to `D3`
- dashboard is currently a compact switchboard; it does not yet expose richer error drill-down or resource anomaly timelines

### Current D3 Phase-1 Landing

- `/api/monitor/leases` now returns:
  - flat `items`
  - `summary`
  - ordered semantic `groups`
- each lease item now carries backend-owned `semantics`:
  - `healthy`
  - `diverged`
  - `orphan`
  - `orphan_diverged`
- the semantic projection now lives in `backend/web/services/monitor_service.py`, while compat monitor route code only delegates
- monitor dashboard and resources page now read those backend semantics instead of recomputing lease meaning from raw `thread.is_orphan` and `desired != observed`

### D3 Remaining Gaps

- semantics are still inferred from current lease row + thread binding only; they do not yet account for stronger lifecycle facts such as historical cleanup windows or explicit terminal/session shutdown markers
- the legacy `/leases` flat table still exists as a drill-down/debug surface, though the monitor resources page now gives a better default entry by rendering only non-empty attention groups and collapsing healthy capacity

### Next D3 Follow-on: Bounded Resource Cleanup

- monitor `Resources` should eventually expose a small cleanup surface for global backlog classes
- first target is not live lease mutation; it is bounded cleanup of rows that already read like backlog:
  - `detached_residue`
  - `orphan_cleanup`
- the cleanup contract must stay backend-owned and explicit:
  - no frontend-only disappearance tricks
  - no silent fallback when cleanup is unsupported
  - no product-page reuse of these controls
- if this lands, it should appear as an operator action inside the global monitor resources surface, close to lease health / residue drill-down, not as a generic product resource affordance

#### Chosen Minimal Approach

- add a monitor-only write endpoint instead of overloading the existing read routes:
  - `POST /api/monitor/resources/cleanup`
- request contract stays narrow and backend-owned:
  - `action`: first slice only `cleanup_residue`
  - `lease_ids`: explicit list of lease ids chosen by the operator
  - `expected_category`: one of `detached_residue` or `orphan_cleanup`
- response contract must be honest and per-lease:
  - `attempted`
  - `cleaned`
  - `skipped`
  - `errors`
  - `refreshed_summary`

#### Landed Backend Slice

- backend route now exists at `POST /api/monitor/resources/cleanup`
- service ownership lives in `backend/web/services/monitor_service.py::cleanup_resource_leases(...)`
- first landed action is still only `cleanup_residue`
- currently landed backend guards:
  - rejects unsupported `action`
  - rejects unsupported `expected_category`
  - re-checks current triage from live monitor rows before mutation
  - refuses to mutate leases that currently classify outside `detached_residue` / `orphan_cleanup`
  - refuses cleanup when live sessions or running commands still exist
  - refuses cleanup when a provider-backed destroy step is still required but unavailable/failing
- current honest boundary:
  - backend contract is live and tested
  - first monitor UI buttons are live
  - broader cleanup ergonomics and bulk controls may still evolve

#### Why This Shape

- it keeps read contracts (`/api/monitor/resources`, `/api/monitor/leases`) clean and cacheable
- it avoids inventing a frontend-owned cleanup heuristic; backend re-checks current triage before mutating anything
- it lets the first slice reuse existing sandbox destruction + lease deletion semantics instead of creating a second cleanup language

#### Backend Rules

- `cleanup_residue` is allowed only when the current backend triage still classifies the lease as:
  - `detached_residue`
  - `orphan_cleanup`
- any lease that currently resolves to `active_drift` or `healthy_capacity` must fail loudly
- first slice does not support bulk heuristics like “all detached residue” without explicit lease ids
- first slice must not silently downgrade to product/session destroy routes if the manager/provider path is missing

#### Cleanup Execution Model

- re-query the current lease truth through the monitor repo and monitor triage helpers before every mutation
- for each accepted lease:
  - if a live provider instance is still attached, destroy it through the provider/manager path first
  - once the lease is no longer in use by terminals/sessions, delete the lease row through the existing lease repo abstraction
- if the lease still has active terminal/session bindings, return an explicit skip/error instead of force-deleting through the repo

#### Frontend First Slice

- add a small cleanup action only inside `Resources -> Lease Health`
- scope it to grouped backlog sections, not the provider detail working surface
- first slice can be as small as:
  - per-row `Cleanup`
  - optional group-level `Cleanup visible residue`
- success state must come from a re-fetch of monitor triage, not optimistic UI removal

#### Landed Frontend Slice

- monitor `Resources -> Lease Health` now exposes per-row `Cleanup` buttons only for:
  - `detached_residue`
  - `orphan_cleanup`
- monitor `Resources -> Lease Health` also now exposes bounded group actions:
  - `Cleanup visible` for the currently rendered `detached_residue` rows
  - `Cleanup visible` for the currently rendered `orphan_cleanup` rows
- no cleanup controls were added to:
  - product `/resources`
  - provider detail working surface
  - `active_drift`
  - `healthy_capacity`
- current UI behavior:
  - clicking `Cleanup` calls `POST /api/monitor/resources/cleanup`
  - clicking `Cleanup visible` first stages an inline confirm row for the current bucket
  - clicking `Confirm cleanup` then sends explicit visible `lease_ids`; it does not invoke a hidden bulk backend mode
  - button goes busy for the targeted lease or targeted visible bucket only
  - result is rendered via an inline feedback strip
  - visible state change comes from a re-fetch of monitor resources/leases, not optimistic removal

### Why this IA

- the backend already exposes `/api/monitor/resources`; the missing piece is a monitor entry surface, not another resource backend invention
- leases are one kind of infrastructure/resource truth, not a top-level product of their own
- traces are usually reached through a thread/run drill-down, so a separate top-level `Traces` tab adds noise before it adds value
