# Legacy Monitor Surfaces PR-C2 Design

**Goal:** Rebind the main monitor pages into the revived sidebar shell so the monitor reads as one operator console instead of a shell wrapped around unrelated documents.

## Position In Sequence

- `PR-C1` is merged at `#262`
  - shell revival
  - route extraction
  - sidebar navigation
- `PR-C2` is the next narrow lane
  - key surfaces rebind
  - no backend contract rewrite
- `PR-C3` remains later
  - density/detail polish
- mandatory companion lane remains separate
  - evaluation runtime activation

## Current Facts

- `dev` now has a real sidebar shell in `frontend/monitor`
- current route set is:
  - `/dashboard`
  - `/threads`
  - `/thread/:threadId`
  - `/resources`
  - `/leases`
  - `/lease/:leaseId`
  - `/diverged`
  - `/events`
  - `/event/:eventId`
- current pages still mostly read like standalone documents mounted inside the shell
- current `ResourcesPage` already has the richest operator structure
- `evaluation` and `traces` are not current mounted monitor routes on `dev`

## Why PR-C2 Exists

`PR-C1` fixed information architecture, not page fit.

That was the right first move, but it leaves an obvious gap:
- the shell looks modern
- the pages still mostly look like legacy standalone views

`PR-C2` closes that gap by making the key surfaces feel native to the shell without changing backend ownership.

## In Scope

- dashboard as a real switchboard surface
- leases page rebind toward drilldown-first operator flow
- resources page alignment with the shell header, sectioning, and lease-first scanning
- threads and events placement cleanup so they match the shell hierarchy
- small shared monitor-page framing components if needed

## Out Of Scope

- backend route changes
- product `/resources`
- identity/runtime rewrites
- full density sweep
- evaluation runtime activation
- reintroducing eval/traces pages without real backend support

## Historical Anchors

These commits matter as source material, not as blind cherry-picks:

- `6adf7f0e` `feat: add monitor dashboard and resources surface`
- `c23dfb2e` `feat: tighten monitor resources surface`
- `d476818d` `feat: split monitor resources into rail and detail`
- `d7cbe8c7` `feat: add monitor lease drilldown panel`

## Design Direction

### Dashboard

Current dashboard is too thin.

`PR-C2` should turn it into a real switchboard:
- one summary band for current monitor truth
- one section for runtime navigation
- one section for operator attention

It does not need new backend data if current `/api/monitor/dashboard` is enough for a first honest pass.

### Resources

Resources is already the strongest surface.

`PR-C2` should not rewrite its data logic.
It should only make it feel structurally native to the shell:
- stronger section boundaries
- clearer relation between provider cards, provider detail, and lease/session drilldown
- consistent page framing with other monitor pages

### Leases

Leases should move away from “flat table first”.

The target is:
- top summary / triage framing first
- then the table
- then drilldown entry that feels consistent with the resources lease detail layer

No backend contract changes are required for that first pass.

### Threads And Events

These can stay simpler in this PR.

The main need is structural consistency:
- page titles and summaries should match shell framing
- detail pages should read like drilldown surfaces, not raw dumps

## Proposed Execution Split

### Slice 1: dashboard + page-frame adapters

- introduce shared page-frame primitives if needed
- rebind dashboard to use them
- align shell-page spacing and summary bands

### Slice 2: leases + resources shell-native structure

- rework leases page composition
- tighten resources section hierarchy without rewriting resource data contracts

### Slice 3: threads/events consistency pass

- make thread/event list/detail pages fit the same console grammar

## Merge Bar

- key monitor pages no longer feel like shell-wrapped leftovers
- no backend contracts change
- no eval-runtime claim sneaks into this PR
- build passes
- targeted frontend route/browser proof passes

## Explicit Evaluation Boundary

Evaluation is still part of the overall monitor recovery story.

But for this PR:
- do not fake an evaluation comeback with dead nav
- do not reintroduce eval pages unless real routes are deliberately added
- keep evaluation runtime activation as a separate mandatory lane coordinated with the upstream owner
