# Monitor Local Proxy Honesty Design

## Goal

Make the standalone monitor frontend use the same local-dev backend port truth as the current worktree, instead of hardcoding `127.0.0.1:8001`.

## Current Facts

- `frontend/monitor/vite.config.ts` still hardcodes:
  - dev server proxy target: `http://127.0.0.1:8001`
  - dev server port: `5174`
  - preview port: `4174`
- `frontend/monitor/package.json` also hardcodes:
  - `vite --port 5174`
  - `vite preview --port 4174`
- `frontend/monitor/README.md` still tells the user:
  - backend is expected at `127.0.0.1:8001`
- `frontend/app/vite.config.ts` already has the honest local-dev pattern:
  - `LEON_BACKEND_PORT`
  - `git config --worktree --get worktree.ports.backend`
- the current worktree already has:
  - `worktree.ports.backend=8012`
  - `worktree.ports.frontend=5184`

So monitor can still open a truthful shell against a false backend target.

## Scope Check

This lane must stay narrow. It is about local-dev honesty only.

If it grows, it will start mixing:

- backend/runtime changes
- monitor UI behavior changes
- product app behavior
- automatic environment discovery logic

That would turn a simple local-dev seam into another broad frontend/backend PR. This lane should not do that.

## Approaches

### 1. Keep hardcoded monitor defaults

Leave monitor on `8001 / 5174 / 4174`.

Pros:
- zero code churn

Cons:
- keeps the current local-dev lie
- diverges from app’s already-established worktree-aware pattern

Rejected.

### 2. Replace hardcoded values with different hardcoded values

Point monitor at the currently observed backend port.

Pros:
- very small diff

Cons:
- still dishonest as soon as another worktree uses a different port
- just moves the hardcoding

Rejected.

### 3. Align monitor with the app’s worktree-aware port resolution

Use the same local-dev truth sources the app already uses:

- backend target from:
  - `LEON_BACKEND_PORT`
  - `worktree.ports.backend`
  - fallback `8001`
- monitor dev port from:
  - `LEON_MONITOR_PORT`
  - `worktree.ports.monitor-frontend`
  - fallback `5174`
- monitor preview port from:
  - `LEON_MONITOR_PREVIEW_PORT`
  - `worktree.ports.monitor-preview`
  - fallback `4174`

Pros:
- truthful local-dev behavior
- matches an existing pattern already in the repo
- keeps scope entirely frontend-local

Cons:
- slightly more code than a hardcoded replacement
- introduces two new optional worktree keys for monitor-specific ports

Recommended.

## Recommended Design

Apply the app’s local-dev port resolution pattern to the standalone monitor frontend, but keep it monitor-specific where needed.

The concrete shape is:

- `frontend/monitor/vite.config.ts`
  - add `getWorktreePort(...)`
  - resolve backend target through env/worktree config/fallback
  - resolve monitor dev port through env/worktree config/fallback
  - resolve monitor preview port through env/worktree config/fallback
- `frontend/monitor/package.json`
  - stop forcing `--port 5174` and `--port 4174`
  - let Vite config own the resolved ports
- `frontend/monitor/README.md`
  - stop claiming backend is always `127.0.0.1:8001`
  - document the env vars and worktree config keys that now control local ports

## Configuration Decisions

### Backend target

Monitor should read backend target in this order:

1. `process.env.LEON_BACKEND_PORT`
2. `git config --worktree --get worktree.ports.backend`
3. fallback `8001`

This keeps monitor aligned with the app and avoids inventing a second backend-port convention.

### Monitor-specific frontend ports

Monitor should not reuse `worktree.ports.frontend`, because that key already belongs to the product app frontend in this worktree.

So monitor gets its own optional keys:

- `worktree.ports.monitor-frontend`
- `worktree.ports.monitor-preview`

And matching env overrides:

- `LEON_MONITOR_PORT`
- `LEON_MONITOR_PREVIEW_PORT`

If they are absent, monitor keeps today’s defaults:

- dev `5174`
- preview `4174`

## Error Handling

Do not add port auto-detection or fallback probing.

If the resolved backend port is wrong:

- the proxy should fail loudly
- the frontend should surface the real request failure

This lane is about making local configuration honest, not hiding configuration mistakes.

## Testing

This lane only needs narrow verification:

- frontend monitor build still passes
- Vite config resolves backend target from env/worktree config correctly
- Vite config resolves monitor dev/preview ports correctly
- README examples match actual resolution behavior

## Merge Bar

This PR is done when:

- monitor no longer hardcodes `/api -> 127.0.0.1:8001`
- monitor no longer hardcodes `5174 / 4174` in package scripts
- monitor local-dev docs describe the real env/worktree config contract
- no backend/product/UI scope was mixed in
