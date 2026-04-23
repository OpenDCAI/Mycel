# Mycel Sandbox Monitor

This is a standalone frontend for Mycel's sandbox monitoring APIs.

Dev:

```bash
cd frontend/monitor
npm install
npm run dev
```

Local ports resolve in this order:

- backend proxy target:
  - `LEON_BACKEND_PORT`
  - `git config --worktree --get worktree.ports.backend`
  - default `8001`
- monitor backend proxy target:
  - `LEON_MONITOR_BACKEND_PORT`
  - `git config --worktree --get worktree.ports.monitor-backend`
  - otherwise use the resolved main backend port
- monitor dev server:
  - `LEON_MONITOR_PORT`
  - `git config --worktree --get worktree.ports.monitor-frontend`
  - default `5174`
- monitor preview server:
  - `LEON_MONITOR_PREVIEW_PORT`
  - `git config --worktree --get worktree.ports.monitor-preview`
  - default `4174`

The Vite proxy splits `/api/monitor/*` and other `/api/*` traffic using those ports, and still fails loudly if they are wrong. This only fixes local-dev honesty; it does not auto-detect or heal bad config.

Open: `http://localhost:5174`

Build:

```bash
npm run build
```
