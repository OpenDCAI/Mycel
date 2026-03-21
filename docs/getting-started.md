# Getting Started with Mycel

Mycel is a proactive AI coding assistant with persistent memory, a terminal UI (TUI), and a web interface. It supports multiple LLM providers and features sandboxed code execution, time-travel debugging, and multi-agent communication.

## Installation

Requires Python 3.12 or later.

### From PyPI

```bash
pip install leonai
```

Or with [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv tool install leonai
```

### From Source

```bash
git clone https://github.com/Ju-Yi-AI-Lab/leonai.git
cd leonai
uv tool install .
```

### Optional Extras

Install extras for additional capabilities:

```bash
# PDF and PowerPoint file reading
pip install "leonai[docs]"

# Sandbox providers
pip install "leonai[sandbox]"     # AgentBay
pip install "leonai[e2b]"         # E2B
pip install "leonai[daytona]"     # Daytona

# Observability
pip install "leonai[langfuse]"
pip install "leonai[langsmith]"

# Everything
pip install "leonai[all]"
```

## First Run and Configuration

Launch Mycel for the first time:

```bash
leonai
```

If no API key is detected, the interactive config wizard starts automatically. It asks for three things:

1. **API_KEY** (required) -- Your OpenAI-compatible API key. This is stored as `OPENAI_API_KEY`.
2. **BASE_URL** (optional) -- The API endpoint. Defaults to `https://api.openai.com/v1`. The wizard auto-appends `/v1` if you omit it.
3. **MODEL_NAME** (optional) -- The model to use. Defaults to `claude-sonnet-4-5-20250929`.

You can re-run the wizard any time:

```bash
leonai config
```

To view current configuration:

```bash
leonai config show
```

Configuration is stored in `~/.leon/config.env` as simple `KEY=VALUE` pairs.

## LLM Provider Setup

Mycel uses the OpenAI-compatible API format. Any provider that speaks this protocol works out of the box.

### Configuration Methods

**Method 1: Config file** (recommended for persistent setup)

Run `leonai config` and enter your provider's API key and base URL.

**Method 2: Environment variables** (overrides config file)

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4o"
```

Environment variables take precedence over `~/.leon/config.env`.

### Provider Examples

#### OpenAI

```
API_KEY:    sk-...
BASE_URL:   https://api.openai.com/v1
MODEL_NAME: gpt-4o
```

#### Anthropic Claude (via OpenAI-compatible proxy)

Claude models are used through an OpenAI-compatible proxy (e.g., OpenRouter):

```
API_KEY:    sk-or-...
BASE_URL:   https://openrouter.ai/api/v1
MODEL_NAME: claude-sonnet-4-5-20250929
```

#### DeepSeek

```
API_KEY:    sk-...
BASE_URL:   https://api.deepseek.com/v1
MODEL_NAME: deepseek-chat
```

#### OpenRouter

OpenRouter provides access to many models through a single API:

```
API_KEY:    sk-or-...
BASE_URL:   https://openrouter.ai/api/v1
MODEL_NAME: anthropic/claude-sonnet-4-5-20250929
```

### Web UI Provider Configuration

The Web UI has a Settings page where you can configure providers graphically. Provider credentials are stored in `~/.leon/models.json`, separate from the TUI's `config.env`. The Web UI supports:

- Multiple providers simultaneously (OpenAI, Anthropic, OpenRouter, etc.)
- Virtual model mapping (e.g., `leon:large` maps to a concrete model)
- Per-model provider routing
- Custom model registration and testing

## Your First Conversation (TUI)

Start a new conversation:

```bash
leonai
```

Continue your last conversation:

```bash
leonai -c
```

Resume a specific thread:

```bash
leonai --thread <thread-id>
```

Use a specific model:

```bash
leonai --model gpt-4o
```

Set a working directory:

```bash
leonai --workspace /path/to/project
```

### Thread Management

List all conversations:

```bash
leonai thread ls
```

View conversation history:

```bash
leonai thread history <thread-id>
```

Rewind to a checkpoint (time-travel):

```bash
leonai thread rewind <thread-id> <checkpoint-id>
```

Delete a thread:

```bash
leonai thread rm <thread-id>
```

### Non-interactive Mode

Send a single message without the TUI:

```bash
leonai run "Explain this codebase"
```

Read from stdin:

```bash
echo "Summarize this file" | leonai run --stdin
```

Interactive mode without TUI:

```bash
leonai run -i
```

## Starting the Web UI

The Web UI is a FastAPI backend that serves a browser-based interface with real-time streaming, agent management, and multi-agent chat.

Start the backend server:

```bash
python -m backend.web.main
```

This launches a uvicorn server on port 8001 (default) with auto-reload enabled. The port can be configured via:

- `LEON_BACKEND_PORT` or `PORT` environment variable
- Git worktree config: `git config --worktree worktree.ports.backend 8002`

The Web UI provides features beyond the TUI:

- Visual agent configuration (system prompts, tools, rules, MCP servers)
- Multi-agent chat between humans and AI agents
- Sandbox session management with resource monitoring
- Model and provider settings with live testing
- Real-time streaming of agent responses via SSE

## Sandbox Management

Mycel supports multiple sandbox providers for isolated code execution. Configure them by placing JSON files in `~/.leon/sandboxes/`:

```bash
leonai sandbox            # Open sandbox manager TUI
leonai sandbox ls         # List active sessions
leonai sandbox new docker # Create a new Docker session
leonai sandbox metrics <id>  # View resource usage
```

Supported providers: Docker, AgentBay, E2B, Daytona.

## Next Steps

- [Multi-Agent Chat](multi-agent-chat.md) -- Learn about the Entity-Chat system for human-agent and agent-agent communication
- [Sandbox Configuration](SANDBOX.md) -- Set up sandboxed execution environments
- [Troubleshooting](TROUBLESHOOTING.md) -- Common issues and solutions
