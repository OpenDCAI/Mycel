English | [中文](../zh/configuration.md)

# Mycel Configuration Guide

Mycel uses a split configuration system: **runtime.json** for behavior settings, **models.json** for model/provider identity, and **config.env** for quick API key setup. Each config file follows a three-tier merge with system defaults, user overrides, and project overrides.

## Quick Setup (First Run)

On first launch without an API key, Mycel automatically opens the config wizard:

```bash
leonai config        # Interactive wizard: API key, base URL, model name
leonai config show   # Show current config.env values
```

The wizard writes `~/.leon/config.env` with three values:

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=claude-sonnet-4-5-20250929
```

This is enough to start using Mycel. The sections below cover advanced configuration.

## Config File Locations

Mycel has three separate config domains, each with its own file:

| Domain | Filename | Purpose |
|--------|----------|---------|
| Runtime behavior | `runtime.json` | Tools, memory, MCP, skills, security |
| Model identity | `models.json` | Providers, API keys, virtual model mapping |
| Observation | `observation.json` | Langfuse / LangSmith tracing |
| Quick setup | `config.env` | API key + base URL (loaded to env vars) |
| Sandbox | `~/.leon/sandboxes/<name>.json` | Per-sandbox-provider config |

Each JSON config file is loaded from three tiers (highest priority first):

1. **Project config**: `.leon/<file>` in workspace root
2. **User config**: `~/.leon/<file>` in home directory
3. **System defaults**: Built-in defaults in `config/defaults/`

CLI arguments (`--model`, `--workspace`, etc.) override everything.

### Merge Strategy

- **runtime / memory / tools**: Deep merge across all tiers (fields from higher-priority tiers override lower)
- **mcp / skills**: Lookup merge (first tier that defines it wins, no merging)
- **system_prompt**: Lookup (project > user > system)
- **providers / mapping** (models.json): Deep merge per-key
- **pool** (models.json): Last wins (no list merge)
- **catalog / virtual_models** (models.json): System-only, never overridden

## Runtime Configuration (runtime.json)

Controls agent behavior, tools, memory, MCP, and skills. **Not** where model/provider identity goes (that's `models.json`).

Full structure with defaults (from `config/defaults/runtime.json`):

```json
{
  "context_limit": 0,
  "enable_audit_log": true,
  "allowed_extensions": null,
  "block_dangerous_commands": true,
  "block_network_commands": false,
  "queue_mode": "steer",
  "temperature": null,
  "max_tokens": null,
  "model_kwargs": {},
  "memory": {
    "pruning": {
      "enabled": true,
      "soft_trim_chars": 3000,
      "hard_clear_threshold": 10000,
      "protect_recent": 3,
      "trim_tool_results": true
    },
    "compaction": {
      "enabled": true,
      "reserve_tokens": 16384,
      "keep_recent_tokens": 20000,
      "min_messages": 20
    }
  },
  "system_prompt": null,
  "tools": {
    "filesystem": {
      "enabled": true,
      "tools": {
        "read_file": { "enabled": true, "max_file_size": 10485760 },
        "write_file": true,
        "edit_file": true,
        "list_dir": true
      }
    },
    "search": {
      "enabled": true,
      "max_results": 50,
      "tools": {
        "grep": { "enabled": true, "max_file_size": 10485760 },
        "glob": true
      }
    },
    "web": {
      "enabled": true,
      "timeout": 15,
      "tools": {
        "web_search": {
          "enabled": true,
          "max_results": 5,
          "tavily_api_key": null,
          "exa_api_key": null,
          "firecrawl_api_key": null
        },
        "fetch": {
          "enabled": true,
          "jina_api_key": null
        }
      }
    },
    "command": {
      "enabled": true,
      "tools": {
        "run_command": { "enabled": true, "default_timeout": 120 },
        "command_status": true
      }
    }
  },
  "mcp": {
    "enabled": true,
    "servers": {}
  },
  "skills": {
    "enabled": true,
    "paths": ["~/.leon/skills"],
    "skills": {}
  }
}
```

> **Note:** The file is flat -- there is no `"runtime"` wrapper key. The config loader wraps these fields internally at load time. Fields like `spill_buffer`, `tool_modes`, `workspace_root` are optional overrides not present in the defaults file; see [Tools](#tools) below for details.

### Runtime Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `temperature` | float (0-2) | null (model default) | Sampling temperature |
| `max_tokens` | int | null (model default) | Max output tokens |
| `context_limit` | int | 0 | Context window limit in tokens. 0 = auto-detect from model |
| `enable_audit_log` | bool | true | Enable audit logging |
| `allowed_extensions` | list | null | Restrict file access to these extensions. null = all |
| `block_dangerous_commands` | bool | true | Block dangerous shell commands (rm -rf, etc.) |
| `block_network_commands` | bool | false | Block network commands |

### Memory

**Pruning** trims old tool results to save context space:

| Field | Default | Description |
|-------|---------|-------------|
| `soft_trim_chars` | 3000 | Soft-trim tool results longer than this |
| `hard_clear_threshold` | 10000 | Hard-clear tool results longer than this |
| `protect_recent` | 3 | Keep last N tool messages untrimmed |
| `trim_tool_results` | true | Enable tool result trimming |

**Compaction** summarizes old conversation history via LLM:

| Field | Default | Description |
|-------|---------|-------------|
| `reserve_tokens` | 16384 | Reserve space for new messages |
| `keep_recent_tokens` | 20000 | Keep recent messages verbatim |
| `min_messages` | 20 | Minimum messages before compaction triggers |

### Tools

Each tool group (filesystem, search, web, command) has an `enabled` flag and a `tools` sub-object. Both the group and individual tool must be enabled for the tool to be available.

Available tools and their config-level names:

| Config Name | UI/Tool Catalog Name | Group |
|------------|----------------------|-------|
| `read_file` | Read | filesystem |
| `write_file` | Write | filesystem |
| `edit_file` | Edit | filesystem |
| `list_dir` | list_dir | filesystem |
| `grep` | Grep | search |
| `glob` | Glob | search |
| `web_search` | WebSearch | web |
| `fetch` | WebFetch | web |
| `run_command` | Bash | command |
| `command_status` | - | command |

**Spill buffer** automatically writes large tool outputs to temp files instead of inlining them in conversation. This is an optional override -- it is not part of the system defaults file:

```json
{
  "tools": {
    "spill_buffer": {
      "default_threshold": 50000,
      "thresholds": {
        "Grep": 20000,
        "run_command": 100000
      }
    }
  }
}
```

**Tool modes** can be set per-tool to `"inline"` (default) or `"deferred"`. Also an optional override, not in defaults:

```json
{
  "tools": {
    "tool_modes": {
      "TaskCreate": "deferred",
      "TaskList": "deferred"
    }
  }
}
```

### Example: Project-level runtime.json

`.leon/runtime.json` in your project root:

```json
{
  "allowed_extensions": ["py", "js", "ts", "json", "yaml", "md"],
  "block_dangerous_commands": true,
  "tools": {
    "web": { "enabled": false },
    "command": {
      "tools": {
        "run_command": { "default_timeout": 300 }
      }
    }
  },
  "system_prompt": "You are a Python expert working on a FastAPI project."
}
```

## Models Configuration (models.json)

Controls which model to use, provider credentials, and virtual model mapping.

### Structure

```json
{
  "active": {
    "model": "claude-sonnet-4-5-20250929",
    "provider": null,
    "based_on": null,
    "context_limit": null
  },
  "providers": {
    "anthropic": {
      "api_key": "${ANTHROPIC_API_KEY}",
      "base_url": "https://api.anthropic.com"
    },
    "openai": {
      "api_key": "${OPENAI_API_KEY}",
      "base_url": "https://api.openai.com/v1"
    }
  },
  "mapping": { ... },
  "pool": {
    "enabled": [],
    "custom": [],
    "custom_config": {}
  }
}
```

### Providers

Define API credentials per provider. The `active.provider` field determines which provider's credentials are used:

```json
{
  "providers": {
    "openrouter": {
      "api_key": "${OPENROUTER_API_KEY}",
      "base_url": "https://openrouter.ai/api/v1"
    }
  },
  "active": {
    "model": "anthropic/claude-sonnet-4-5",
    "provider": "openrouter"
  }
}
```

### API Key Resolution

Mycel looks for an API key in this order:
1. Active provider's `api_key` from `models.json`
2. Any provider with an `api_key` in `models.json`
3. Environment variables: `ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > `OPENROUTER_API_KEY`

### Provider Auto-Detection

When no explicit `provider` is set, Mycel auto-detects from environment:
- `ANTHROPIC_API_KEY` set -> provider = `anthropic`
- `OPENAI_API_KEY` set -> provider = `openai`
- `OPENROUTER_API_KEY` set -> provider = `openai`

### Custom Models

Add models not in the built-in catalog via the `pool.custom` list:

```json
{
  "pool": {
    "custom": ["deepseek-chat", "qwen-72b"],
    "custom_config": {
      "deepseek-chat": {
        "based_on": "gpt-4o",
        "context_limit": 65536
      }
    }
  }
}
```

`based_on` tells Mycel which model family to use for tokenizer/context detection. `context_limit` overrides the auto-detected context window.

## Virtual Models

Mycel provides four virtual model aliases (`leon:*`) that map to concrete models with preset parameters:

| Virtual Name | Concrete Model | Provider | Extras | Use Case |
|-------------|---------------|----------|--------|----------|
| `leon:mini` | claude-haiku-4-5-20250929 | anthropic | - | Fast, simple tasks |
| `leon:medium` | claude-sonnet-4-5-20250929 | anthropic | - | Balanced, daily work |
| `leon:large` | claude-opus-4-6 | anthropic | - | Complex reasoning |
| `leon:max` | claude-opus-4-6 | anthropic | temperature=0.0 | Maximum precision |

Usage:

```bash
leonai --model leon:mini
leonai --model leon:large
```

Or in `~/.leon/models.json`:

```json
{
  "active": {
    "model": "leon:large"
  }
}
```

### Overriding Virtual Model Mapping

You can remap virtual models to different concrete models in your user or project `models.json`:

```json
{
  "mapping": {
    "leon:medium": {
      "model": "gpt-4o",
      "provider": "openai"
    }
  }
}
```

When you override just the `model` without specifying `provider`, the inherited provider is cleared (you need to re-specify it if it differs from auto-detection).

## Agent Profiles

Mycel ships with four built-in agent profiles defined as Markdown files with YAML frontmatter:

| Name | Description |
|------|-------------|
| `general` | Full-capability general agent, default sub-agent |
| `bash` | Shell command specialist |
| `explore` | Codebase exploration and analysis |
| `plan` | Task planning and decomposition |

Usage:

```bash
leonai --agent general
leonai --agent explore
```

### Agent File Format

Agents are `.md` files with YAML frontmatter:

```markdown
---
name: my-agent
description: What this agent does
tools:
  - "*"
model: leon:large
---

Your system prompt goes here. This is the body of the Markdown file.
```

Frontmatter fields:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Agent identifier |
| `description` | no | Human-readable description |
| `tools` | no | Tool whitelist. `["*"]` = all tools (default) |
| `model` | no | Model override for this agent |

### Agent Loading Priority

Agents are loaded from multiple directories (later overrides earlier by name):

1. Built-in agents: `config/defaults/agents/*.md`
2. User agents: `~/.leon/agents/*.md`
3. Project agents: `.leon/agents/*.md`
4. Member agents: `~/.leon/members/<id>/agent.md` (highest priority)

## Tool Configuration

The full tool catalog includes tools beyond the runtime.json config groups:

| Tool | Group | Mode | Description |
|------|-------|------|-------------|
| Read | filesystem | inline | Read file contents |
| Write | filesystem | inline | Write file |
| Edit | filesystem | inline | Edit file (exact replacement) |
| list_dir | filesystem | inline | List directory contents |
| Grep | search | inline | Regex search (ripgrep-based) |
| Glob | search | inline | Glob pattern file search |
| Bash | command | inline | Execute shell commands |
| WebSearch | web | inline | Internet search |
| WebFetch | web | inline | Fetch web page with AI extraction |
| Agent | agent | inline | Spawn sub-agent |
| SendMessage | agent | inline | Queue a message for another running agent |
| TaskOutput | agent | inline | Get background task output |
| TaskStop | agent | inline | Stop background task |
| TaskCreate | todo | deferred | Create todo task |
| TaskGet | todo | deferred | Get task details |
| TaskList | todo | deferred | List all tasks |
| TaskUpdate | todo | deferred | Update task status |
| load_skill | skills | inline | Load a skill |
| tool_search | system | inline | Search available tools |

Tools in `deferred` mode run asynchronously without blocking the conversation.

## MCP Configuration

MCP servers are configured in `runtime.json` under the `mcp` key. Each server can use either stdio (command + args) or HTTP transport (url):

```json
{
  "mcp": {
    "enabled": true,
    "servers": {
      "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
          "GITHUB_TOKEN": "${GITHUB_TOKEN}"
        },
        "allowed_tools": null
      },
      "remote-server": {
        "url": "https://mcp.example.com/sse",
        "allowed_tools": ["search", "fetch"]
      }
    }
  }
}
```

MCP server fields:

| Field | Description |
|-------|-------------|
| `command` | Executable to launch (stdio transport) |
| `args` | Command arguments |
| `env` | Environment variables passed to the server process |
| `url` | URL for streamable HTTP transport (alternative to command) |
| `allowed_tools` | Whitelist of tool names. null = all tools exposed |

### Member-level MCP

Members (`~/.leon/members/<id>/`) can have their own `.mcp.json` following the same format as Claude's MCP config:

```json
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": ["-y", "@supabase/mcp-server"],
      "env": { "SUPABASE_URL": "..." }
    }
  }
}
```

## Skills Configuration

```json
{
  "skills": {
    "enabled": true,
    "paths": ["~/.leon/skills", "./skills"],
    "skills": {
      "code-review": true,
      "debugging": false
    }
  }
}
```

Skill paths are directories containing skill subdirectories. Each skill has a `SKILL.md` file. The `skills` map enables/disables individual skills by name.

Skill paths must exist on disk -- the validator requires each directory in `paths` to be present. Mycel does not create them automatically.

## Observation Configuration (observation.json)

Configure observability providers for tracing agent runs:

```json
{
  "active": "langfuse",
  "langfuse": {
    "secret_key": "${LANGFUSE_SECRET_KEY}",
    "public_key": "${LANGFUSE_PUBLIC_KEY}",
    "host": "https://cloud.langfuse.com"
  },
  "langsmith": {
    "api_key": "${LANGSMITH_API_KEY}",
    "project": "leon",
    "endpoint": null
  }
}
```

Set `active` to `"langfuse"`, `"langsmith"`, or `null` (disabled).

## Sandbox Configuration

Sandbox configs live at `~/.leon/sandboxes/<name>.json`. Each file defines a sandbox provider:

```json
{
  "provider": "daytona",
  "on_exit": "pause",
  "daytona": {
    "api_key": "your-key",
    "api_url": "https://app.daytona.io/api",
    "target": "local",
    "cwd": "/home/daytona"
  }
}
```

Supported providers: `local`, `docker`, `e2b`, `daytona`, `agentbay`.

Select at launch:

```bash
leonai --sandbox daytona       # Uses ~/.leon/sandboxes/daytona.json
leonai --sandbox docker        # Uses ~/.leon/sandboxes/docker.json
export LEON_SANDBOX=e2b        # Or set via env var
```

Provider-specific fields:

| Provider | Fields |
|----------|--------|
| docker | `image`, `mount_path`, `docker_host` |
| e2b | `api_key`, `template`, `cwd`, `timeout` |
| daytona | `api_key`, `api_url`, `target`, `cwd` |
| agentbay | `api_key`, `region_id`, `context_path`, `image_id` |

## Environment Variables

### In config.env

`~/.leon/config.env` is a simple key=value file loaded into environment variables at startup (only if the variable is not already set):

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=claude-sonnet-4-5-20250929
```

The `OPENAI_BASE_URL` value is auto-normalized to include `/v1` if missing.

### In JSON config files

All string values in `runtime.json`, `models.json`, and `observation.json` support:

- `${VAR}` -- environment variable expansion
- `~` -- home directory expansion

```json
{
  "providers": {
    "anthropic": {
      "api_key": "${ANTHROPIC_API_KEY}"
    }
  }
}
```

### Relevant Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | API key (OpenAI-compatible format) |
| `OPENAI_BASE_URL` | API base URL |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_BASE_URL` | Anthropic base URL |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `MODEL_NAME` | Override model name |
| `LEON_SANDBOX` | Default sandbox name |
| `LEON_SANDBOX_DB_PATH` | Override sandbox database path |
| `TAVILY_API_KEY` | Tavily web search API key |
| `JINA_API_KEY` | Jina AI fetch API key |
| `EXA_API_KEY` | Exa search API key |
| `FIRECRAWL_API_KEY` | Firecrawl API key |
| `AGENTBAY_API_KEY` | AgentBay API key |
| `E2B_API_KEY` | E2B API key |
| `DAYTONA_API_KEY` | Daytona API key |

## CLI Reference

```bash
leonai                          # Start new session (TUI)
leonai -c                       # Continue last session
leonai --model leon:large       # Override model
leonai --agent explore          # Use agent preset
leonai --workspace /path        # Set workspace root
leonai --sandbox docker         # Use sandbox config
leonai --thread <id>            # Resume specific thread

leonai config                   # Interactive config wizard
leonai config show              # Show current config.env

leonai thread ls                # List all threads
leonai thread history <id>      # Show thread history
leonai thread rewind <id> <cp>  # Rewind to checkpoint
leonai thread rm <id>           # Delete thread

leonai sandbox                  # Sandbox manager TUI
leonai sandbox ls               # List sandbox sessions
leonai sandbox new [provider]   # Create session
leonai sandbox pause <id>       # Pause session
leonai sandbox resume <id>      # Resume session
leonai sandbox rm <id>          # Delete session
leonai sandbox metrics <id>     # Show resource metrics

leonai run "message"            # Non-interactive single message
leonai run --stdin              # Read messages from stdin
leonai run -i                   # Interactive mode (no TUI)
leonai run -d                   # With debug output
```
