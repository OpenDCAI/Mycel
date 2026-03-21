🇬🇧 English | [🇨🇳 中文](../zh/sandbox.md)

# Sandbox

Mycel's sandbox system runs agent operations (file I/O, shell commands) in isolated environments instead of the host machine. Five providers are supported: **Local** (host passthrough), **Docker** (container), **E2B** (cloud), **Daytona** (cloud or self-hosted), and **AgentBay** (Alibaba Cloud).

## Quick Start (Web UI)

### 1. Configure a Provider

Go to **Settings → Sandbox** in the Web UI. You'll see cards for each provider. Expand a card and fill in the required fields:

| Provider | Required Fields |
|----------|----------------|
| **Docker** | Image name (default: `python:3.12-slim`), mount path |
| **E2B** | API key |
| **Daytona** | API key, API URL |
| **AgentBay** | API key |

Click **Save**. The configuration is stored in `~/.leon/sandboxes/<provider>.json`.

### 2. Create a Thread with Sandbox

When starting a new conversation, use the **sandbox dropdown** in the top-left of the input area. Select your configured provider (e.g. `docker`). Then type your message and send.

The thread is bound to that sandbox at creation — all subsequent agent runs in this thread use the same sandbox.

### 3. Monitor Resources

Go to the **Resources** page (sidebar icon). You'll see:

- **Provider cards** — status (active/ready/unavailable) for each provider
- **Sandbox cards** — each running/paused sandbox with agent avatars, duration, and metrics (CPU/RAM/Disk)
- **Detail sheet** — click a sandbox card to see agents using it, detailed metrics, and a file browser

## Example Configurations

See [`examples/sandboxes/`](../../examples/sandboxes/) for ready-to-use config templates for all providers. Copy to `~/.leon/sandboxes/` or configure directly in the Web UI Settings.

## Provider Configuration

### Docker

Requires Docker installed on the host. No API key needed.

```json
{
  "provider": "docker",
  "docker": {
    "image": "python:3.12-slim",
    "mount_path": "/workspace"
  },
  "on_exit": "pause"
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `docker.image` | `python:3.12-slim` | Docker image |
| `docker.mount_path` | `/workspace` | Working directory inside container |
| `on_exit` | `pause` | `pause` (preserve state) or `destroy` (clean slate) |

### E2B

Cloud sandbox service. Requires an [E2B](https://e2b.dev) API key.

```json
{
  "provider": "e2b",
  "e2b": {
    "api_key": "e2b_...",
    "template": "base",
    "cwd": "/home/user",
    "timeout": 300
  },
  "on_exit": "pause"
}
```

### Daytona

Supports both [Daytona](https://daytona.io) SaaS and self-hosted instances.

**SaaS:**
```json
{
  "provider": "daytona",
  "daytona": {
    "api_key": "dtn_...",
    "api_url": "https://app.daytona.io/api",
    "cwd": "/home/daytona"
  },
  "on_exit": "pause"
}
```

**Self-hosted:**
```json
{
  "provider": "daytona",
  "daytona": {
    "api_key": "dtn_...",
    "api_url": "https://your-server.com/api",
    "target": "local",
    "cwd": "/home/daytona"
  },
  "on_exit": "pause"
}
```

### AgentBay

Alibaba Cloud sandbox (China region). Requires an AgentBay API key.

```json
{
  "provider": "agentbay",
  "agentbay": {
    "api_key": "akm-...",
    "region_id": "ap-southeast-1",
    "context_path": "/home/wuying"
  },
  "on_exit": "pause"
}
```

### Extra Dependencies

Cloud sandbox providers require extra Python packages:

```bash
uv sync --extra sandbox     # AgentBay
uv sync --extra e2b         # E2B
uv sync --extra daytona     # Daytona
```

Docker works out of the box (uses the Docker CLI).

### API Key Resolution

API keys are resolved in order:

1. Config file field (`e2b.api_key`, `daytona.api_key`, etc.)
2. Environment variable (`E2B_API_KEY`, `DAYTONA_API_KEY`, `AGENTBAY_API_KEY`)
3. `~/.leon/config.env`

## Session Lifecycle

Each thread is bound to one sandbox. Sessions follow a lifecycle:

```
idle → active → paused → destroyed
```

### `on_exit` Behavior

| Value | Behavior |
|-------|----------|
| `pause` | Pause session on exit. Resume on next startup. Files, packages, processes preserved. |
| `destroy` | Kill session on exit. Clean slate next time. |

`pause` is the default — you keep everything across restarts.

### Web UI Session Management

From the **Resources** page:

- View all sessions across all providers in a unified grid
- Click a session card → detail sheet with metrics + file browser
- Pause / Resume / Destroy via API (endpoints below)

**API Endpoints:**

| Action | Endpoint |
|--------|----------|
| List resources | `GET /api/monitor/resources` |
| Force refresh | `POST /api/monitor/resources/refresh` |
| Pause session | `POST /api/sandbox/sessions/{id}/pause?provider={type}` |
| Resume session | `POST /api/sandbox/sessions/{id}/resume?provider={type}` |
| Destroy session | `DELETE /api/sandbox/sessions/{id}?provider={type}` |

## CLI Reference

For terminal-based sandbox management, see the [CLI docs](cli.md#sandbox-management).

Summary of CLI commands:

```bash
leonai sandbox              # TUI manager
leonai sandbox ls           # List sessions
leonai sandbox new docker   # Create session
leonai sandbox pause <id>   # Pause
leonai sandbox resume <id>  # Resume
leonai sandbox rm <id>      # Delete
leonai sandbox metrics <id> # Show metrics
```

## Architecture

The sandbox is an infrastructure layer below the middleware stack. It provides backends that existing middleware uses:

```
Agent
  ├── sandbox.fs()    → FileSystemBackend  (used by FileSystemMiddleware)
  └── sandbox.shell() → BaseExecutor       (used by CommandMiddleware)
```

Middleware owns **policy** (validation, path rules, hooks). The backend owns **I/O** (where operations execute). Swapping the backend changes where operations happen without touching middleware logic.

### Session Tracking

Sessions are tracked in SQLite (`~/.leon/sandbox.db`):

| Table | Purpose |
|-------|---------|
| `sandbox_leases` | Lease lifecycle — provider, desired/observed state |
| `sandbox_instances` | Provider-side session IDs |
| `abstract_terminals` | Virtual terminals bound to thread + lease |
| `lease_resource_snapshots` | CPU, memory, disk metrics |

Thread → sandbox mapping goes through `abstract_terminals.thread_id` → `abstract_terminals.lease_id`.
