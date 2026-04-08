# Legacy Monitor Surfaces PR-C2 Implementation Plan

**Goal:** Rebind the current monitor pages into the revived sidebar shell so the dashboard, resources, leases, threads, and events surfaces read as one console.

**Architecture:** This plan keeps backend contracts fixed. It works in three bounded frontend-only slices: first establish shared page framing and a real dashboard switchboard, then rebind leases/resources into shell-native structure, then align threads/events detail surfaces with the same console grammar. Evaluation runtime activation stays outside this plan.

**Tech Stack:** React 19, React Router 7, TypeScript, Vite, Vitest, CSS

---

## Mandatory Boundary

- No backend route changes
- No product `/resources`
- No identity/runtime rewrites
- No fake evaluation comeback
- No PR-C3 density sweep in this PR

## Task 1: Add PR-C2 surface smoke tests

**Files:**
- Modify: `frontend/monitor/src/app/routes.test.tsx`
- Test: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`

- [ ] Add failing smoke expectations for:
  - dashboard switchboard framing
  - shell-native leases/resources headings
  - page-level consistency markers
- [ ] Run route smoke to verify the new expectations fail
- [ ] Commit:

```bash
git add frontend/monitor/src/app/routes.test.tsx
git commit -m "test: lock monitor surface rebind smoke"
```

## Task 2: Rebind dashboard as a real switchboard

**Files:**
- Modify: `frontend/monitor/src/pages/DashboardPage.tsx`
- Create or modify shared shell-page primitives if needed
- Modify: `frontend/monitor/src/styles.css`
- Test:
  - `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
  - `cd frontend/monitor && npm run build`

- [ ] Replace the thin dashboard body with switchboard structure that uses current backend truth only
- [ ] Keep dashboard honest if backend data is thin or unavailable
- [ ] Verify tests/build
- [ ] Commit:

```bash
git add frontend/monitor/src/pages/DashboardPage.tsx frontend/monitor/src/styles.css frontend/monitor/src/app
git commit -m "feat: rebind monitor dashboard into console switchboard"
```

## Task 3: Rebind leases and resources into shell-native sections

**Files:**
- Modify: `frontend/monitor/src/pages/LeasesPage.tsx`
- Modify: `frontend/monitor/src/pages/LeaseDetailPage.tsx`
- Modify: `frontend/monitor/src/ResourcesPage.tsx`
- Modify: `frontend/monitor/src/styles.css`
- Test:
  - `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
  - `cd frontend/monitor && npm run build`

- [ ] Move leases away from flat-table-first framing
- [ ] Tighten resources section hierarchy without changing resource data contracts
- [ ] Keep current browse/detail/resource wiring intact
- [ ] Verify tests/build
- [ ] Commit:

```bash
git add frontend/monitor/src/pages/LeasesPage.tsx frontend/monitor/src/pages/LeaseDetailPage.tsx frontend/monitor/src/ResourcesPage.tsx frontend/monitor/src/styles.css
git commit -m "feat: rebind monitor runtime surfaces"
```

## Task 4: Align threads and events with console drilldown grammar

**Files:**
- Modify: `frontend/monitor/src/pages/ThreadsPage.tsx`
- Modify: `frontend/monitor/src/pages/ThreadDetailPage.tsx`
- Modify: `frontend/monitor/src/pages/EventsPage.tsx`
- Modify: `frontend/monitor/src/pages/EventDetailPage.tsx`
- Modify: `frontend/monitor/src/styles.css`
- Test:
  - `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
  - `cd frontend/monitor && npm run build`

- [ ] Align list/detail framing with the shell-native page structure
- [ ] Do not widen into backend/event semantics work
- [ ] Verify tests/build
- [ ] Commit:

```bash
git add frontend/monitor/src/pages/ThreadsPage.tsx frontend/monitor/src/pages/ThreadDetailPage.tsx frontend/monitor/src/pages/EventsPage.tsx frontend/monitor/src/pages/EventDetailPage.tsx frontend/monitor/src/styles.css
git commit -m "feat: align monitor drilldown surfaces"
```

## Task 5: Browser proof and PR prep

**Files:**
- No required code files
- Update PR description/checkpoint as needed

- [ ] Run fresh browser proof on the rebuilt pages
- [ ] Record honest boundary if data routes are unavailable in local proof
- [ ] Prepare draft PR as `PR-C2`

## Verification Standard

- `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
- `cd frontend/monitor && npm run build`
- browser proof for:
  - `/dashboard`
  - `/resources`
  - `/leases`
  - at least one list/detail pair from threads/events

## Hard Stopline

- This plan does not restore evaluation runtime
- This plan does not add evaluation nav unless real route support exists
- If evaluation needs to come back, open or continue the separate mandatory companion lane instead of expanding `PR-C2`
