# Mycel Deployment Guide

English | [中文](../zh/deployment.md)

## Prerequisites

### Required
- Python 3.11 or higher
- `uv` package manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- Git

### Optional (by provider)
- **Docker**: Docker daemon for local sandbox provider
- **E2B**: API key from [e2b.dev](https://e2b.dev)
- **Daytona**: API key from [daytona.io](https://daytona.io) or self-hosted instance
- **AgentBay**: API key and region access

---

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/leonai.git
cd leonai
```

### 2. Install Dependencies

```bash
# Install all dependencies including sandbox providers
uv pip install -e ".[all]"

# Or install specific providers only
uv pip install -e ".[e2b]"      # E2B only
uv pip install -e ".[daytona]"  # Daytona only
uv pip install -e ".[sandbox]"  # All sandbox providers
```

---

## Configuration

### User Config Directory

Mycel stores configuration in `~/.leon/`:

```
~/.leon/
├── config.json          # Main configuration
├── config.env           # Environment variables
├── models.json          # LLM provider mappings
├── sandboxes/           # Sandbox provider configs
│   ├── docker.json
│   ├── e2b.json
│   ├── daytona_saas.json
│   └── daytona_selfhost.json
└── leon.db              # SQLite database
```

### Environment Variables

Create `~/.leon/config.env`:

```bash
# LLM Provider (OpenRouter example)
ANTHROPIC_API_KEY=your_openrouter_key
ANTHROPIC_BASE_URL=https://openrouter.ai/api/v1

# Sandbox Providers
E2B_API_KEY=your_e2b_key
DAYTONA_API_KEY=your_daytona_key
AGENTBAY_API_KEY=your_agentbay_key

# Optional: Supabase (if using remote storage)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key
```

---

## Sandbox Provider Setup

### Local (Default)

No configuration needed. Uses local filesystem.

```bash
# Test local sandbox
leon --sandbox local
```

### Docker

**Requirements:** Docker daemon running

Create `~/.leon/sandboxes/docker.json`:

```json
{
  "provider": "docker",
  "on_exit": "destroy",
  "docker": {
    "image": "python:3.11-slim",
    "mount_path": "/workspace"
  }
}
```

**Troubleshooting:**
- If Docker CLI hangs, check proxy environment variables
- Mycel strips `http_proxy`/`https_proxy` when calling Docker CLI
- Use `docker_host` config to override Docker socket path

### E2B

**Requirements:** E2B API key

Create `~/.leon/sandboxes/e2b.json`:

```json
{
  "provider": "e2b",
  "on_exit": "pause",
  "e2b": {
    "api_key": "${E2B_API_KEY}",
    "template": "base",
    "cwd": "/home/user",
    "timeout": 300
  }
}
```

### Daytona SaaS

**Requirements:** Daytona account and API key

Create `~/.leon/sandboxes/daytona_saas.json`:

```json
{
  "provider": "daytona",
  "on_exit": "pause",
  "daytona": {
    "api_key": "${DAYTONA_API_KEY}",
    "api_url": "https://app.daytona.io/api",
    "target": "local",
    "cwd": "/home/daytona"
  }
}
```

### Daytona Self-Hosted

**Requirements:** Self-hosted Daytona instance

**Critical:** Self-hosted Daytona requires:
1. Runner container with bash at `/usr/bin/bash`
2. Workspace image with bash at `/usr/bin/bash`
3. Runner on bridge network (for workspace container access)
4. Daytona Proxy accessible on port 4000 (for file operations)

Create `~/.leon/sandboxes/daytona_selfhost.json`:

```json
{
  "provider": "daytona",
  "on_exit": "pause",
  "daytona": {
    "api_key": "${DAYTONA_API_KEY}",
    "api_url": "http://localhost:3986/api",
    "target": "us",
    "cwd": "/workspace"
  }
}
```

**Docker Compose Configuration:**

```yaml
services:
  daytona-runner:
    image: your-runner-image-with-bash
    environment:
      - RUNNER_DOMAIN=runner  # NOT localhost!
    networks:
      - default
      - bridge  # Required for workspace access
    # ... other config

networks:
  bridge:
    external: true
```

**Network Configuration:**

The runner must be on both the compose network AND the default bridge network where workspace containers run. Add to `/etc/hosts` on runner:

```
127.0.0.1 proxy.localhost
```

**Troubleshooting:**
- "fork/exec /usr/bin/bash: no such file" → Workspace image missing bash
- "Failed to create sandbox within 60s" → Network isolation, check runner networks
- File operations fail → Daytona Proxy (port 4000) not accessible

### AgentBay

**Requirements:** AgentBay API key and region access

Create `~/.leon/sandboxes/agentbay.json`:

```json
{
  "provider": "agentbay",
  "on_exit": "pause",
  "agentbay": {
    "api_key": "${AGENTBAY_API_KEY}",
    "region_id": "ap-southeast-1",
    "context_path": "/home/wuying"
  }
}
```

---

## Verification

### Health Check

```bash
# Check Mycel installation
leon --version

# List available sandboxes
leonai sandbox ls

# Test sandbox provider
leon --sandbox docker
```

### Test Command Execution

```python
from sandbox import SandboxConfig, create_sandbox

config = SandboxConfig.load("docker")
sbx = create_sandbox(config)

# Create session
session = sbx.create_session()

# Execute command
result = sbx.execute(session.session_id, "echo 'Hello from sandbox'")
print(result.output)

# Cleanup
sbx.destroy_session(session.session_id)
```

---

## Common Issues

### "Could not import module 'main'"

Backend startup failed. Check:
- Are you in the correct directory?
- Is the virtual environment activated?
- Use full path to uvicorn: `.venv/bin/uvicorn`

### "SOCKS proxy error" from LLM client

Shell environment has `all_proxy=socks5://...` set. Unset before starting:

```bash
env -u ALL_PROXY -u all_proxy uvicorn main:app
```

### Docker provider hangs

Proxy environment variables inherited by Docker CLI. Mycel strips these automatically, but if issues persist, check `docker_host` configuration.

### Daytona PTY bootstrap fails

Check:
1. Workspace image has bash at `/usr/bin/bash`
2. Runner has bash at `/usr/bin/bash`
3. Runner is on bridge network
4. Daytona Proxy (port 4000) is accessible

---

## Production Deployment

### Database

Mycel uses SQLite by default (`~/.leon/leon.db`). For production:

1. **Backup regularly:**
   ```bash
   cp ~/.leon/leon.db ~/.leon/leon.db.backup
   ```

2. **Consider PostgreSQL** for multi-user deployments (requires code changes)

### Security

- Store API keys in `~/.leon/config.env`, never in code
- Use environment variable substitution in config files: `"${API_KEY}"`
- Restrict file permissions: `chmod 600 ~/.leon/config.env`

### Monitoring

- Backend logs: Check stdout/stderr from uvicorn
- Sandbox logs: Provider-specific (Docker logs, E2B dashboard, etc.)
- Database: Monitor `~/.leon/leon.db` size and query performance

---

## Next Steps

- See [SANDBOX.md](../sandbox/SANDBOX.md) for detailed sandbox provider documentation
- See [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) for common issues and solutions
- See example configs in `examples/sandboxes/`
