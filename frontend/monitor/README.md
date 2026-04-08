# Leon Sandbox Monitor

This is a standalone frontend for Leon's sandbox monitoring APIs.

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
  - fallback `8001`
- monitor dev server:
  - `LEON_MONITOR_PORT`
  - `git config --worktree --get worktree.ports.monitor-frontend`
  - fallback `5174`
- monitor preview server:
  - `LEON_MONITOR_PREVIEW_PORT`
  - `git config --worktree --get worktree.ports.monitor-preview`
  - fallback `4174`

The Vite `/api` proxy still fails loudly if these ports are wrong. This only fixes local-dev honesty; it does not auto-detect or heal bad config.

Open: `http://localhost:5174`

Build:

```bash
npm run build
```
