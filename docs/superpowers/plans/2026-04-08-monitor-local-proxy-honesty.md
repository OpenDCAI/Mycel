# Monitor Local Proxy Honesty Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the standalone monitor frontend resolve local backend/dev/preview ports from env and worktree config instead of hardcoded values.

**Architecture:** Keep this lane frontend-local. Reuse the app’s existing worktree-aware backend-port pattern, introduce monitor-specific optional port keys for the standalone frontend, and update local-dev docs to match the real behavior.

**Tech Stack:** Vite, React frontend config, Vitest, npm

---

## File Structure

- Modify: `frontend/monitor/vite.config.ts`
  - add worktree-aware port resolution
- Modify: `frontend/monitor/package.json`
  - stop overriding config ports with hardcoded CLI flags
- Modify: `frontend/monitor/README.md`
  - document real local-dev port contract
- Create: `frontend/monitor/vite.config.test.ts`
  - lock env/worktree port resolution behavior

## Mandatory Boundary

- No backend changes
- No monitor UI changes
- No product app changes
- No auto-detection or probing
- No config fallback hiding

## Task 1: Lock monitor Vite resolution behavior

**Files:**
- Create: `frontend/monitor/vite.config.test.ts`
- Modify: `frontend/monitor/vite.config.ts`
- Modify: `frontend/monitor/package.json`
- Test:
  - `cd frontend/monitor && npm test -- --run vite.config.test.ts`

- [ ] Add a failing test that proves monitor resolves:
  - backend target from `LEON_BACKEND_PORT` before worktree config
  - monitor dev port from `LEON_MONITOR_PORT` before worktree config
  - monitor preview port from `LEON_MONITOR_PREVIEW_PORT` before worktree config
  - fallback values when no env/worktree config exists
- [ ] Run the targeted test and verify it fails.
- [ ] Implement the smallest config change:
  - add `getWorktreePort(...)`
  - export a small helper for resolved config values so the test can read them
  - remove hardcoded `--port` flags from `package.json` so Vite config actually owns the ports
- [ ] Re-run the targeted test and verify it passes.
- [ ] Re-run monitor build and verify it still passes:
  - `cd frontend/monitor && npm run build`
- [ ] Commit:

```bash
git add frontend/monitor/vite.config.ts frontend/monitor/vite.config.test.ts frontend/monitor/package.json
git commit -m "feat: align monitor local vite ports with worktree config"
```

## Task 2: Lock README honesty

**Files:**
- Modify: `frontend/monitor/README.md`
- Test:
  - `cd frontend/monitor && npm run build`

- [ ] Update README so it no longer claims backend is always `127.0.0.1:8001`.
- [ ] Document the real local-dev contract:
  - `LEON_BACKEND_PORT`
  - `LEON_MONITOR_PORT`
  - `LEON_MONITOR_PREVIEW_PORT`
  - `worktree.ports.backend`
  - `worktree.ports.monitor_frontend`
  - `worktree.ports.monitor_preview`
- [ ] Keep the wording narrow:
  - local-dev honesty only
  - no claim that monitor auto-discovers or heals wrong ports
- [ ] Re-run monitor build as a quick guard:
  - `cd frontend/monitor && npm run build`
- [ ] Commit:

```bash
git add frontend/monitor/README.md
git commit -m "docs: document monitor local port contract"
```

## Task 3: Verification and PR prep

**Files:**
- No required code files

- [ ] Run:
  - `cd frontend/monitor && npm test -- --run vite.config.test.ts`
  - `cd frontend/monitor && npm run build`
- [ ] Record the honest boundary:
  - this PR only fixes local-dev proxy/port honesty
  - wrong configured ports still fail loudly
- [ ] Prepare a narrow draft PR

## Hard Stopline

- Do not touch backend routes
- Do not touch app Vite config
- Do not add dynamic port probing
- Do not expand this into monitor runtime or product behavior work
