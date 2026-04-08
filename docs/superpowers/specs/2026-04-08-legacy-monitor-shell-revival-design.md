# Legacy Monitor Shell Revival Design

**Goal:** Restore the legacy monitor shell as a staged frontend workstream, starting with a unified left-sidebar console shell that reorganizes existing monitor surfaces without reopening backend or identity scope.

## Why This Exists

- `#210` originally carried a much larger monitor frontend sweep, but that work was cut back before merge.
- `#260` and `#261` stabilized the resource-observability lane and actor-first payload contracts.
- The next required lane is the legacy monitor shell/frontend revival, but it must not be smuggled back in as one giant PR.

This design turns that revival into an explicit sequence instead of another oversized transplant.

## Current Facts

- Current `dev` contains working monitor resource contracts and resource UI surfaces from `#260`.
- Current `dev` does not contain the earlier full monitor shell sweep that introduced the left sidebar, deeper hierarchy, and denser console structure.
- The historical monitor frontend sweep still exists in git history and can be used as lineage/anchor material.
- Relevant legacy anchors include:
  - `bcaebc82` `feat: modernize monitor console shell`
  - `8786db96` `feat: deepen monitor console hierarchy`
  - `d328c346` `feat: modernize monitor shell chrome`
  - `16b317fe` `feat: group monitor sidebar navigation`
  - `d476818d` `feat: split monitor resources into rail and detail`
  - `d7cbe8c7` `feat: add monitor lease drilldown panel`
  - `e5e9013a` `feat: sharpen monitor sidebar rail grouping`
  - `5e826dee` `feat: tighten monitor lease detail density`
  - `16059ddb` `feat: tighten evaluation status density`
  - `57df3156` `feat: tighten monitor evaluation split density`

## Constraints

- Do not reopen product `/resources`; that remains a separate lane.
- Do not reopen identity/runtime rewrites; `#259` remains the owning lane for that.
- Do not change monitor backend contracts as part of shell revival.
- Do not merge shell revival, page rebind, and density polish into one PR.
- Keep existing `/api/monitor/*` route ownership and page data-fetch boundaries intact unless a later PR explicitly changes them.

## Proposal Comparison

### Proposal A: Shell-only revival

- Restore the left sidebar, shell chrome, and route hierarchy.
- Leave page interiors mostly untouched.

Pros:
- Smallest and safest first step.
- Very easy to review.

Cons:
- Can feel incomplete because the shell improves before the key page structures catch up.

### Proposal B: Shell plus key surfaces

- Restore the shell and immediately rebind `resources`, `leases`, `traces`, and `evaluation` into the revived information architecture.

Pros:
- Closest to the historical monitor sweep.
- Higher user-facing value.

Cons:
- Too large for a single PR if done in one pass.

### Proposal C: Full legacy transplant

- Bring back shell, hierarchy, rail/detail splits, density, and detail polish in one shot.

Why it loses:
- Review surface becomes too large.
- Regression isolation becomes poor.
- Risks repeating the same “too big, cut back later” failure mode as the earlier lane.

## Chosen Direction

Use Proposal B as the overall workstream, but execute it as three explicit PRs:

1. `PR-C1` shell revival
2. `PR-C2` key surfaces rebind
3. `PR-C3` density/detail polish

This keeps the end-state ambitious while keeping each merge slice narrow.

## Sequence Of PRs

### `PR-C1` shell revival

**Goal**
- Restore monitor as a unified console shell with a left sidebar and stable route hierarchy.

**Includes**
- `MonitorShell`
- `MonitorNav`
- grouped left-sidebar navigation
- route organization for:
  - `resources`
  - `leases`
  - `traces`
  - `evaluation`
- shell chrome, titles, and content framing

**Does not include**
- major backend changes
- page-internal density overhauls
- product route work

**Merge bar**
- left sidebar exists and is the primary navigation
- key monitor routes are reachable through the shell
- current page data still flows from existing `/api/monitor/*` routes
- monitor build passes
- browser proof shows sidebar, route switching, and title/content changes

### `PR-C2` key surfaces rebind

**Goal**
- Rebind the main monitor surfaces into the revived console structure so they feel native to the shell rather than embedded legacy pages.

**Includes**
- `resources` rail/detail re-organization
- `leases` drilldown structure
- `traces` placement within the shell hierarchy
- `evaluation` shell alignment

**Does not include**
- density polish across every table/panel
- identity/runtime rewrites

**Merge bar**
- the four main surfaces look and behave like one console, not separate documents
- route hierarchy remains coherent
- backend contracts stay intact
- route/browser smoke proof remains green

### `PR-C3` density/detail polish

**Goal**
- Bring back the stronger information density and detail views from the historical sweep after the shell and page structure are stable.

**Includes**
- denser tables
- tighter detail panels
- sidebar grouping polish
- evaluation and lease detail density

**Merge bar**
- density improves readability without breaking shell structure
- no contract churn
- browser proof shows the intended hierarchy still holds after polish

## `PR-C1` Architecture

### Components

- `MonitorShell`
  - owns page frame, content container, page title chrome
- `MonitorNav`
  - owns nav grouping, labels, active state
- `monitor-nav.ts`
  - static navigation model and grouping metadata
- route adapters
  - keep existing page-level data logic and only adapt them into the shell

### File Boundaries

Target structure:

- `frontend/monitor/src/app/MonitorShell.tsx`
- `frontend/monitor/src/app/MonitorNav.tsx`
- `frontend/monitor/src/app/monitor-nav.ts`
- `frontend/monitor/src/app/routes.tsx`
- existing page files under `frontend/monitor/src/pages/...`
- `frontend/monitor/src/styles.css` for shell-level layout variables and styling

The shell should not become a new monolith. Navigation model, shell frame, and page adapters should remain separate.

### Data Flow

- URL selects route
- route mounts page inside `MonitorShell`
- page keeps its current fetch path
- shell does not take ownership of page data

That means:
- `resources` keeps using `/api/monitor/resources`
- `leases` keeps using `/api/monitor/leases`
- `traces` and `evaluation` keep their current route contracts

### Error Handling

- shell does not swallow page-specific errors
- page loading/empty/error states remain page-owned
- shell only handles structure and navigation

If a page is still thin or awkward, that is a `PR-C2` problem, not a reason to overbuild `PR-C1`.

## Visual Direction

- light console shell, not a dark dashboard clone
- clear left rail with grouped ops navigation
- dense enough for operator work, but not yet the final density pass
- resources, leases, traces, and evaluation should read as one product family

## Non-goals

- Replacing current monitor backend routes
- Reopening product resources
- Full Daytona-style clone
- One-shot restoration of every legacy visual detail
- Sneaking `PR-C2` or `PR-C3` work into `PR-C1`

## Verification

### `PR-C1`

- `cd frontend/monitor && npm run build`
- route-level monitor smoke remains green
- browser proof:
  - sidebar visible
  - route switching works
  - `/resources`, `/leases`, `/traces`, `/evaluation` all render under the unified shell

### `PR-C2`

- shell still builds and routes correctly
- browser proof for rail/detail and drilldown structure on the main surfaces

### `PR-C3`

- shell and routes remain stable after density changes
- browser proof compares before/after density without route regressions

## Risk Notes

- The main risk is scope creep, not implementation difficulty.
- The fix is structural: keep the three PRs separate and do not borrow future-slice work into the current one.
- If a reviewer starts asking for density tweaks during `PR-C1`, those should be logged for `PR-C3`, not folded in immediately.
