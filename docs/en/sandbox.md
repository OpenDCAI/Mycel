# Sandbox

English | [中文](../zh/sandbox.md)

LEON's sandbox system runs agent operations (file I/O, shell commands) in isolated environments instead of the host machine. Four providers are supported: **Docker** (local container), **E2B** (cloud), **Daytona** (cloud or self-hosted), and **AgentBay** (Alibaba cloud).

## Quick Start

```bash
# Run LEON in a Docker container
leonai --sandbox docker

# Run LEON in E2B cloud sandbox
leonai --sandbox e2b

# Run LEON in Daytona cloud sandbox
leonai --sandbox daytona

# Run LEON in AgentBay cloud sandbox
leonai --sandbox agentbay

# Headless mode
leonai run --sandbox docker "List files in the workspace"

# Inspect and manage sandbox sessions
leonai sandbox              # TUI manager
leonai sandbox ls           # List sessions
leonai sandbox new docker   # Create session
leonai sandbox pause <id>   # Pause session
leonai sandbox resume <id>  # Resume session
leonai sandbox rm <id>      # Delete session
leonai sandbox metrics <id> # Show resource metrics
leonai sandbox destroy-all-sessions  # Destroy everything
```

## Configuration

### Config Files

Each sandbox provider is configured via a JSON file in `~/.leon/sandboxes/`:

```
~/.leon/sandboxes/
├── docker.json
├── e2b.json
├── daytona.json
└── agentbay.json
```

The file name (minus `.json`) is the sandbox name you pass to `--sandbox`.

### Docker

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
| `docker.image` | `python:3.12-slim` | Docker image to use |
| `docker.mount_path` | `/workspace` | Working directory inside container |
| `on_exit` | `pause` | What to do on agent exit: `pause` or `destroy` |

**Requirements:** Docker CLI available on the host.

### E2B

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

| Field | Default | Description |
|-------|---------|-------------|
| `e2b.api_key` | — | E2B API key (or set `E2B_API_KEY` env var) |
| `e2b.template` | `base` | E2B sandbox template |
| `e2b.cwd` | `/home/user` | Working directory |
| `e2b.timeout` | `300` | Session timeout in seconds |
| `on_exit` | `pause` | `pause` or `destroy` |

### Daytona

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

| Field | Default | Description |
|-------|---------|-------------|
| `daytona.api_key` | — | Daytona API key (or set `DAYTONA_API_KEY` env var) |
| `daytona.api_url` | `https://app.daytona.io/api` | Daytona API base URL |
| `daytona.cwd` | `/home/daytona` | Working directory |
| `on_exit` | `pause` | `pause` or `destroy` |

### AgentBay

```json
{
  "provider": "agentbay",
  "agentbay": {
    "region_id": "ap-southeast-1",
    "context_path": "/home/wuying",
    "image_id": null
  },
  "on_exit": "pause"
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `agentbay.api_key` | — | AgentBay API key (or set `AGENTBAY_API_KEY` env var) |
| `agentbay.region_id` | `ap-southeast-1` | Cloud region |
| `agentbay.context_path` | `/home/wuying` | Working directory |
| `agentbay.image_id` | `null` | Specific image (optional) |
| `on_exit` | `pause` | `pause` or `destroy` |

### API Key Resolution

API keys are resolved in order:

1. Config file field (`e2b.api_key`, `agentbay.api_key`)
2. Environment variable (`E2B_API_KEY`, `AGENTBAY_API_KEY`)
3. `~/.leon/config.env` (loaded automatically)

To set keys in `config.env`:

```bash
leonai config
# Or manually edit ~/.leon/config.env:
# AGENTBAY_API_KEY=akm-...
# E2B_API_KEY=e2b_...
```

### Sandbox Name Resolution

The sandbox name is resolved in order:

1. CLI flag: `leonai --sandbox docker`
2. Auto-detection: when resuming a thread (`--thread` or `-c`), the system looks up the provider from SQLite
3. Environment variable: `LEON_SANDBOX=docker`
4. Default: `local` (no sandbox, runs on host)

Auto-detection means you don't need to pass `--sandbox` again when resuming a thread that previously used a sandbox. If the sandbox config file is missing or the session was destroyed, it falls back to local mode silently.

## Session Lifecycle

Sessions are managed per conversation thread:

```
First tool call in thread "abc"
  → Create new sandbox session
  → Map thread "abc" → session_id in SQLite

Agent exit (on_exit="pause")
  → Pause all running sessions
  → Sessions preserved for next startup

Next startup, same thread
  → Resume paused session
  → State intact (files, installed packages, etc.)
```

### `on_exit` Behavior

| Value | Behavior |
|-------|----------|
| `pause` | Pause sessions on exit. Resume on next startup. State preserved. |
| `destroy` | Kill sessions on exit. Clean slate next time. |

`pause` is the default and recommended for development — you keep installed packages, created files, and running processes across LEON restarts.

## Session Management

### CLI Commands

All TUI operations are available as CLI subcommands:

```bash
# List all sessions across all providers
leonai sandbox ls

# Create a new session (picks first available provider if omitted)
leonai sandbox new
leonai sandbox new docker
leonai sandbox new e2b

# Pause / resume / delete (accepts session ID prefix)
leonai sandbox pause iolzc
leonai sandbox resume iolzc
leonai sandbox rm iolzc

# Show CPU, memory, disk, network metrics
leonai sandbox metrics iolzc

# Destroy all sessions (requires confirmation)
leonai sandbox destroy-all-sessions
```

Session IDs can be abbreviated — any unique prefix works.

### TUI Manager

```bash
leonai sandbox
```

Opens a full-screen TUI for managing sessions interactively.

### Layout

```
┌─────────────────────────────────────────────────────┐
│ Sandbox Session Manager                             │
├──────────┬──────────────────────────────────────────┤
│ Refresh  │ Session ID  │ Status  │ Provider │ Thread│
│ New      │ abc123...   │ running │ docker   │ tui-1 │
│ Delete   │ def456...   │ paused  │ e2b      │ tui-2 │
│ Pause    │ ghi789...   │ running │ agentbay │ run-3 │
│ Resume   │             │         │          │       │
│ Metrics  │             │         │          │       │
│ Open URL │             │         │          │       │
├──────────┴──────────────────────────────────────────┤
│ Select a session to view details                    │
├─────────────────────────────────────────────────────┤
│ Found 3 session(s)                                  │
└─────────────────────────────────────────────────────┘
```

### Keybindings

| Key | Action |
|-----|--------|
| `r` | Refresh session list |
| `n` | Create new session (uses first available provider) |
| `d` | Delete selected session |
| `p` | Pause selected session |
| `u` | Resume selected session |
| `m` | Show metrics (CPU, memory, disk, network) |
| `o` | Open web URL in browser (AgentBay only) |
| `q` | Quit |

### Provider Discovery

The manager loads providers from all `~/.leon/sandboxes/*.json` config files. If a provider's API key is missing, that provider is silently skipped. Sessions from all available providers are shown in a single unified table.

### Pause/Resume Support

Some providers or account tiers don't support pause/resume. When this is detected (via `BenefitLevel.NotSupport` error), the Pause and Resume buttons are muted with "(N/A)" for that session. This is cached per session.

### Metrics

Selecting a session and pressing `m` shows:

## Daytona

`daytona` supports both Daytona SaaS and self-hosted Daytona. This is config-only: set `daytona.api_url`.

- Default (SaaS): `daytona.api_url` is `https://app.daytona.io/api`
- Self-hosted: set `daytona.api_url` to your own server (must include `/api`, e.g. `https://daytona.example.com/api`)

Example `~/.leon/sandboxes/daytona.json` (self-hosted):
```json
{
  "provider": "daytona",
  "daytona": {
    "api_key": "dtn_...",
    "api_url": "https://daytona.example.com/api",
    "target": "local",
    "cwd": "/home/daytona"
  },
  "on_exit": "pause"
}
```

```
Session: abc123...
CPU: 45.2%
Memory: 512MB / 2048MB
Disk: 10.5GB / 100GB
Network: RX 1.2 KB/s | TX 0.8 KB/s

Web URL: https://...  (AgentBay only)
```

Docker metrics come from `docker stats`. AgentBay metrics come from the cloud API. E2B does not provide metrics.

## Architecture

### How It Works

The sandbox is an **infrastructure layer** below the middleware stack. It doesn't own tools — it provides **backends** that existing middleware uses:

```
LeonAgent
  │
  ├── sandbox.fs()    → FileSystemBackend  (used by FileSystemMiddleware)
  └── sandbox.shell() → BaseExecutor       (used by CommandMiddleware)
```

Middleware owns **policy** (hooks, validation, path rules). The backend owns **I/O mechanism** (where operations actually execute). Swapping the backend changes where operations happen without touching middleware logic.

Both `FileSystemBackend` and `BaseExecutor` ABCs have an `is_remote` property (default `False`). Sandbox backends set `is_remote = True`, which middleware uses to skip local-only logic (e.g. `Path.resolve()`, `mkdir`, hooks).

For local mode, `sandbox.fs()` and `sandbox.shell()` return `None`, so middleware falls back to `LocalBackend` (host filesystem) and OS-detected shell (zsh/bash/powershell).

Provider command results use `ProviderExecResult` (sandbox/provider.py), which `SandboxExecutor` translates to the middleware's `ExecuteResult` (middleware/command/base.py).

### File Layout

```
sandbox/
├── __init__.py          # Factory: create_sandbox()
├── base.py              # Abstract Sandbox interface
├── config.py            # SandboxConfig, provider configs, DEFAULT_DB_PATH
├── capability.py        # Provider capability detection
├── chat_session.py      # Chat session lifecycle
├── lease.py             # Lease state machine
├── lifecycle.py         # Sandbox lifecycle orchestration
├── manager.py           # SandboxManager (session orchestration)
├── provider.py          # SandboxProvider ABC, ProviderExecResult, Metrics
├── provider_events.py   # Provider event handling
├── resource_snapshot.py # Resource metric snapshots
├── runtime.py           # Runtime environment
├── shell_output.py      # Shell output processing
├── terminal.py          # Abstract terminal management
├── thread_context.py    # ContextVar for thread_id tracking
└── providers/
    ├── agentbay.py      # AgentBayProvider (Alibaba SDK)
    ├── daytona.py       # DaytonaProvider (Daytona SDK, SaaS or self-hosted)
    ├── docker.py        # DockerProvider (Docker CLI)
    ├── e2b.py           # E2BProvider (E2B SDK)
    └── local.py         # LocalProvider (host passthrough)

middleware/
├── filesystem/
│   ├── backend.py           # FileSystemBackend ABC (is_remote property)
│   ├── local_backend.py     # LocalBackend (host fs)
│   └── sandbox_backend.py   # SandboxFileBackend (is_remote=True)
└── command/
    ├── base.py              # BaseExecutor ABC (is_remote property)
    └── sandbox_executor.py  # SandboxExecutor (is_remote=True)
```

### Two-Layer Abstraction

**Sandbox** (e.g. `DockerSandbox`) bundles a filesystem backend + shell executor + session management for a given environment.

**Provider** (e.g. `DockerProvider`) is the actual API client that talks to Docker CLI / E2B SDK / AgentBay SDK.

The Sandbox layer handles session caching, thread context, and lifecycle. The Provider layer handles raw API calls.

### Session Tracking

Sessions are tracked in SQLite (`~/.leon/sandbox.db`) across several tables:

| Table | Purpose |
|-------|---------|
| `sandbox_leases` | Lease lifecycle — one lease per sandbox environment. Tracks provider, desired/observed state, instance binding. |
| `sandbox_instances` | Provider-side session IDs bound to a lease. |
| `lease_events` | Audit log of lease state transitions. |
| `abstract_terminals` | Virtual terminals bound to a thread + lease. Tracks cwd and env delta. |
| `thread_terminal_pointers` | Maps each thread to its active and default terminal. |
| `chat_sessions` | Conversation sessions linking thread, terminal, and lease with TTL/budget. |
| `terminal_commands` | Command history per terminal (stdin, stdout, stderr, exit code). |
| `terminal_command_chunks` | Streaming stdout/stderr chunks for long-running commands. |
| `provider_events` | Raw events received from providers (for reconciliation). |
| `lease_resource_snapshots` | CPU, memory, disk metrics per lease (written by resource monitor). |

Thread-to-sandbox mapping goes through `abstract_terminals.thread_id` + `abstract_terminals.lease_id` (there is no `thread_id` column on `sandbox_leases`).

The standalone `lookup_sandbox_for_thread()` function enables sandbox auto-detection when resuming threads — it does a pure SQLite lookup without initializing any provider.

## Headless Testing

The sandbox can be tested end-to-end without the TUI:

```bash
# Single message
leonai run --sandbox docker -d "Run echo hello"

# Interactive
leonai run --sandbox e2b -i

# Programmatic (Python)
from agent import create_leon_agent
agent = create_leon_agent(sandbox="docker")
result = agent.invoke("List files", thread_id="test-1")
agent.close()
```

See `tests/test_sandbox_e2e.py` for the full test suite.
