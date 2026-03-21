# Mycel

<div align="center">

<img src="./assets/banner.png" alt="Mycel Banner" width="600">

**Production-ready agent runtime for building, running, and governing collaborative AI teams**

🇬🇧 English | [🇨🇳 中文](docs/README_CN.md)

[![PyPI version](https://badge.fury.io/py/leonai.svg)](https://badge.fury.io/py/leonai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

</div>

---

Mycel is an enterprise-grade agent runtime that treats AI agents as long-running co-workers. Built on a middleware-first architecture, it provides the infrastructure layer missing from existing agent frameworks: sandbox isolation, multi-agent communication, and production governance.

## Why Mycel?

Existing agent frameworks focus on *building* agents. Mycel focuses on *running* them in production:

- **Middleware Pipeline**: Unified tool injection, validation, security, and observability
- **Sandbox Isolation**: Run agents in Docker/E2B/cloud with automatic state management
- **Multi-Agent Communication**: Agents discover, message, and collaborate with each other — and with humans
- **Production Governance**: Built-in security controls, audit logging, and cost tracking

## Quick Start

### Installation

```bash
pip install leonai
```

Or with uv (recommended):

```bash
uv tool install leonai
```

### First Run

```bash
leonai
```

On first launch, Mycel will guide you through configuration. You'll need an OpenAI-compatible API key.

### Minimal Configuration

Create `~/.leon/config.json`:

```json
{
  "api": {
    "api_key": "${OPENAI_API_KEY}",
    "model": "leon:balanced"
  }
}
```

### Your First Conversation

```bash
leonai
```

```
You: What files are in the current directory?
Agent: [Uses list_dir tool]
Found 12 files: README.md, pyproject.toml, src/, tests/, ...

You: Read the README and summarize it
Agent: [Uses read_file tool]
This project is...
```

## Core Concepts

### Middleware Pipeline

Every tool interaction flows through a 10-layer middleware stack:

```
User Request
    ↓
┌─────────────────────────────────────┐
│ 1. Steering (Queue injection)       │
│ 2. Prompt Caching                   │
│ 3. File System (read/write/edit)    │
│ 4. Search (grep/find)               │
│ 5. Web (search/fetch)               │
│ 6. Command (shell execution)        │
│ 7. Skills (dynamic loading)         │
│ 8. Todo (task tracking)             │
│ 9. Task (sub-agents)                │
│10. Monitor (observability)          │
└─────────────────────────────────────┘
    ↓
Tool Execution → Result + Metrics
```

### Sandbox Isolation

Agents run in isolated environments with managed lifecycles:

**Lifecycle**: `idle → active → paused → destroyed`

**Supported Providers**:
- **Local**: Direct host access (development)
- **Docker**: Containerized isolation (testing)
- **E2B**: Cloud sandboxes (production)
- **AgentBay**: Alibaba Cloud (China region)

### Configuration System

Three-layer configuration merge:

```
System Defaults → User Config → Project Config → CLI Args
```

**Virtual Models**:
```bash
leonai --model leon:fast       # Sonnet, temp=0.7
leonai --model leon:balanced   # Sonnet, temp=0.5
leonai --model leon:powerful   # Opus, temp=0.3
leonai --model leon:coding     # Opus, temp=0.0
```

### Agent Profiles

```bash
leonai --agent coder        # Code development
leonai --agent researcher   # Research (read-only)
leonai --agent tester       # QA testing
```

## Features

### TUI Interface

Modern terminal interface with keyboard shortcuts:

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line |
| `Ctrl+↑/↓` | Browse history |
| `Ctrl+Y` | Copy last message |
| `Ctrl+E` | Export conversation |
| `Ctrl+L` | Clear history |
| `Ctrl+T` | Switch thread |
| `ESC ESC` | History browser |

### Web UI

Full-featured web interface:

```bash
leonai web
# Opens http://localhost:8000
```

**Features**:
- Real-time chat with multiple agents
- Sandbox resource dashboard
- Token usage and cost tracking
- Thread history and search

### Multi-Agent Communication

Agents are first-class social entities. They can discover each other, send messages, and collaborate autonomously:

```
Member (template)
  └→ Entity (social identity — agents and humans both get one)
       └→ Thread (agent brain / conversation)
```

- **`chat_send`**: Agent A messages Agent B; B responds autonomously
- **`directory`**: Agents browse and discover other entities
- **`tell_owner`**: Agents escalate to their human owner
- **Real-time delivery**: SSE-based chat with typing indicators and read receipts

Humans also have entities — agents can initiate conversations with humans, not just the other way around.

### File Upload & Workspace Sync

Upload files to agent workspace and sync changes ([PR #130](https://github.com/OpenDCAI/leonai/pull/130)):

```bash
# Upload files via Web UI
# Files persist across sandbox restarts
```

**Use Cases**:
- Upload datasets for analysis
- Share code files with agents
- Persist configuration files
- Download agent-generated artifacts

### MCP Integration

Connect external services:

```json
{
  "mcp": {
    "servers": {
      "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
        "allowed_tools": ["create_issue", "list_issues"]
      }
    }
  }
}
```

### Skills System

Load expertise on demand:

```bash
You: Load the code-review skill
Agent: Skill loaded. I can now perform detailed code reviews.
```

### Multi-Sandbox Support

| Provider | Use Case | Cost |
|----------|----------|------|
| **Local** | Development | Free |
| **Docker** | Testing | Free |
| **E2B** | Production | $0.15/hr |
| **AgentBay** | China Region | ¥1/hr |

```bash
leonai --sandbox docker
leonai sandbox ls
leonai sandbox pause <id>
```

### Security & Governance

- Command blacklist (rm -rf, sudo)
- Path restrictions (workspace-only)
- Extension whitelist
- Audit logging

## Architecture

**Middleware Stack**: 10-layer pipeline for unified tool management

**Sandbox Lifecycle**: `idle → active → paused → destroyed`

**Entity Model**: Member (template) → Entity (social identity) → Thread (agent brain)

**Relationships**: Member (1:N) → Thread (N:1) → Sandbox

## Roadmap

**Completed** ✓
- Configuration system, TUI, MCP, Skills
- Multi-provider sandboxes
- Web UI with dashboard
- File upload/download ([PR #130](https://github.com/OpenDCAI/leonai/pull/130))
- Multi-agent communication (Entity-Chat)

**In Progress** 🚧
- Hook system, Plugin ecosystem
- Agent evaluation

## Documentation

- [Getting Started](docs/getting-started.md) — Installation, LLM provider setup, first run
- [Configuration](docs/config/configuration.md) — Config files, virtual models, tool settings
- [Multi-Agent Chat](docs/multi-agent-chat.md) — Entity-Chat system, agent communication
- [Sandbox](docs/sandbox/SANDBOX.md) — Providers, lifecycle, session management
- [Deployment](docs/deployment/DEPLOYMENT.md) — Production deployment guide
- [Concepts](docs/product-primitives.md) — Core abstractions (Thread, Member, Task, Resource)

## Contributing

```bash
git clone https://github.com/OpenDCAI/leonai.git
cd leonai
uv sync
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

MIT License
