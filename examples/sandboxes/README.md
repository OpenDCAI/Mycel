# Sandbox Configuration Examples

Working configuration templates for all supported sandbox providers. These are sanitized versions of real production configs.

## Usage

### Web UI (recommended)

Go to **Settings → Sandbox** in the Mycel Web UI. The form fields match these JSON structures.

### Manual Setup

Copy the desired config to `~/.leon/sandboxes/`:

```bash
mkdir -p ~/.leon/sandboxes
cp examples/sandboxes/docker.json ~/.leon/sandboxes/docker.json
```

## Available Providers

| File | Provider | Requirements | Cost |
|------|----------|--------------|------|
| `docker.json` | Docker (local container) | Docker daemon | Free |
| `e2b.json` | E2B (cloud) | E2B API key | $0.15/hr |
| `daytona_saas.json` | Daytona SaaS | Daytona account | Free tier available |
| `daytona_selfhost.json` | Daytona (self-hosted) | Your own Daytona instance | Free |
| `agentbay.json` | AgentBay (Alibaba Cloud) | AgentBay API key | ~¥1/hr |

## API Keys

Set API keys via environment variables or in `~/.leon/config.env`:

```bash
E2B_API_KEY=e2b_xxxxxxxxxxxx
DAYTONA_API_KEY=dtn_xxxxxxxxxxxx
AGENTBAY_API_KEY=akm-xxxxxxxxxxxx
```

Config files support `${VAR_NAME}` syntax for environment variable substitution.

## See Also

- [Sandbox Documentation](../../docs/en/sandbox.md) — Provider details, lifecycle, monitoring
- [CLI Reference](../../docs/en/cli.md) — `leonai sandbox` commands
