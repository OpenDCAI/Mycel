# Evaluation Monitor Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mount a dedicated monitor evaluation page that truthfully renders the existing `/api/monitor/evaluation` operator payload.

**Architecture:** This plan keeps `PR-D2` frontend-only. It adds one mounted route, one sidebar entry, and one page component that consumes the already-shipped operator truth from `PR-D1/#264`. It does not widen into runtime activation, trace drilldown, or backend contract changes.

**Tech Stack:** React 19, React Router 7, TypeScript, Vitest, Vite, CSS

---

## File Structure

- Create: `frontend/monitor/src/pages/EvaluationPage.tsx`
  - mounted operator surface for `/evaluation`
- Modify: `frontend/monitor/src/app/routes.tsx`
  - register `/evaluation`
- Modify: `frontend/monitor/src/app/monitor-nav.ts`
  - add nav entry
- Modify: `frontend/monitor/src/app/routes.test.tsx`
  - lock route mounting, nav highlight, unavailable copy
- Modify: `frontend/monitor/src/styles.css`
  - add only the minimal styles needed for the evaluation surface

## Mandatory Boundary

- No backend route or payload changes
- No evaluation runtime activation claims
- No traces drilldown
- No product-facing evaluation UI
- No dashboard rewrite beyond existing summary consumption

## Task 1: Lock route smoke for the evaluation surface

**Files:**
- Modify: `frontend/monitor/src/app/routes.test.tsx`
- Test: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`

- [ ] Add failing route smoke for the new monitor evaluation surface:
  - sidebar renders `Evaluation`
  - `/evaluation` mounts inside `MonitorShell`
  - evaluation nav item becomes current
  - unavailable operator truth is visible on the page
- [ ] Run route smoke and verify the new assertions fail
- [ ] Commit:

```bash
git add frontend/monitor/src/app/routes.test.tsx
git commit -m "test: lock monitor evaluation surface smoke"
```

## Task 2: Mount the evaluation route and nav entry

**Files:**
- Modify: `frontend/monitor/src/app/routes.tsx`
- Modify: `frontend/monitor/src/app/monitor-nav.ts`
- Create: `frontend/monitor/src/pages/EvaluationPage.tsx`
- Test: `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`

- [ ] Add `/evaluation` to `MonitorRoutes`
- [ ] Add `Evaluation` to the sidebar nav using the existing monitor nav grammar
- [ ] Create `EvaluationPage` with the same fetch/error/loading pattern used by other monitor pages
- [ ] Render the truthful operator headline/summary for the current unavailable payload
- [ ] Run route smoke and verify it passes
- [ ] Commit:

```bash
git add frontend/monitor/src/app/routes.tsx frontend/monitor/src/app/monitor-nav.ts frontend/monitor/src/pages/EvaluationPage.tsx frontend/monitor/src/app/routes.test.tsx
git commit -m "feat: mount monitor evaluation surface"
```

## Task 3: Add minimal operator-surface sections

**Files:**
- Modify: `frontend/monitor/src/pages/EvaluationPage.tsx`
- Modify: `frontend/monitor/src/styles.css`
- Test:
  - `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
  - `cd frontend/monitor && npm run build`

- [ ] Add a compact status/summary header
- [ ] Add artifact-summary cards driven by `artifact_summary`
- [ ] Add facts grid driven by `facts`
- [ ] Add artifacts table driven by `artifacts`
- [ ] Add ordered `next_steps`
- [ ] Add raw-notes block only when `raw_notes` is present
- [ ] Keep unavailable state honest; do not invent zero-state success copy
- [ ] Run route smoke and build
- [ ] Commit:

```bash
git add frontend/monitor/src/pages/EvaluationPage.tsx frontend/monitor/src/styles.css frontend/monitor/src/app/routes.test.tsx
git commit -m "feat: flesh out monitor evaluation operator surface"
```

## Task 4: Proof and PR prep

**Files:**
- No required code files
- Update PR description/checkpoint as needed

- [ ] Run fresh browser proof for `/evaluation`
- [ ] Record the honest boundary if the payload is still `status=unavailable`
- [ ] Prepare draft PR as `PR-D2`

## Verification Standard

- `cd frontend/monitor && npm test -- --run src/app/routes.test.tsx`
- `cd frontend/monitor && npm run build`
- browser proof for `/evaluation` inside the revived shell

## Hard Stopline

- This plan does not activate evaluation runtime
- This plan does not add trace drilldown
- This plan does not change `/api/monitor/evaluation`
- If the operator payload proves insufficient, stop and open a bounded backend follow-up instead of silently expanding `PR-D2`
