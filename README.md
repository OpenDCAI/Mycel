# Mycel

<div align="center">

<img src="./assets/banner.png" alt="Mycel Banner" width="600">

**Production-ready agent runtime for building, running, and governing collaborative AI teams**

🇬🇧 English | [🇨🇳 中文](README.zh.md)

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

### Prerequisites

- Python 3.11+
- Node.js 18+
- An OpenAI-compatible API key

### 1. Get the source

```bash
git clone https://github.com/OpenDCAI/Mycel.git
cd Mycel
```

### 2. Install dependencies

```bash
# Backend (Python)
uv sync

# Frontend
cd frontend/app && npm install && cd ../..
```

**Sandbox providers** require extra dependencies — install only what you need:

```bash
uv sync --extra sandbox     # AgentBay
uv sync --extra e2b         # E2B
uv sync --extra daytona     # Daytona
```

Docker sandbox works out of the box (just needs Docker installed). See [Sandbox docs](docs/en/sandbox.md) for provider setup.

### 3. Start the services

```bash
# Terminal 1: Backend
uv run python -m backend.web.main
# → http://localhost:8001

# Terminal 2: Frontend
cd frontend/app && npm run dev
# → http://localhost:5173
```

### 4. Open and configure

1. Open **http://localhost:5173** in your browser
2. **Register** an account
3. Go to **Settings** → configure your LLM provider (API key, model)
4. Start chatting with your first agent

## Features

### Web Interface

Full-featured web platform for managing and interacting with agents:

- Real-time chat with multiple agents
- Multi-agent communication — agents message each other autonomously
- Sandbox resource dashboard
- Token usage and cost tracking
- File upload and workspace sync
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
- **Real-time delivery**: SSE-based chat with typing indicators and read receipts

Humans also have entities — agents can initiate conversations with humans, not just the other way around.

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

| Provider | Use Case | Cost |
|----------|----------|------|
| **Local** | Development | Free |
| **Docker** | Testing | Free |
| **Daytona** | Production (cloud or self-hosted) | Free (self-host) |
| **E2B** | Production | $0.15/hr |
| **AgentBay** | China Region | ¥1/hr |

### Extensibility: MCP & Skills

Agents can be extended with external tools and specialized expertise:

- **MCP (Model Context Protocol)** — Connect external services (GitHub, databases, APIs) via the [MCP standard](https://modelcontextprotocol.io). Configure per-member in the Web UI or via `.mcp.json`.
- **Skills** — Load domain expertise on demand. Skills inject specialized prompts and tool configurations into agent sessions. Managed through the Web UI member settings.

### Security & Governance

- Command blacklist (rm -rf, sudo)
- Path restrictions (workspace-only)
- Extension whitelist
- Audit logging

## Architecture

**Middleware Stack**: 10-layer pipeline for unified tool management

**Sandbox Lifecycle**: `idle → active → paused → destroyed`

**Entity Model**: Member (template) → Entity (social identity) → Thread (agent brain)

## Documentation

- [CLI Reference](docs/en/cli.md) — Terminal interface, commands, LLM provider setup
- [Configuration](docs/en/configuration.md) — Config files, virtual models, tool settings
- [Multi-Agent Chat](docs/en/multi-agent-chat.md) — Entity-Chat system, agent communication
- [Sandbox](docs/en/sandbox.md) — Providers, lifecycle, session management
- [Deployment](docs/en/deployment.md) — Production deployment guide
- [Concepts](docs/en/product-primitives.md) — Core abstractions (Thread, Member, Task, Resource)

## Contributing

```bash
git clone https://github.com/OpenDCAI/Mycel.git
cd Mycel
uv sync
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

MIT License
