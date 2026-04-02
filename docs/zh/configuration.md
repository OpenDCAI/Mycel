[English](../en/configuration.md) | 中文

# Mycel 配置指南

Mycel 使用分离式配置系统：**runtime.json** 控制行为设置，**models.json** 控制模型/提供商身份，**config.env** 用于快速 API 密钥设置。每个配置文件遵循三层合并策略：系统默认值、用户覆盖和项目覆盖。

## 快速设置（首次运行）

首次启动时如果没有 API 密钥，Mycel 会自动打开配置向导：

```bash
leonai config        # 交互式向导：API 密钥、Base URL、模型名称
leonai config show   # 显示当前 config.env 的值
```

向导会将三个值写入 `~/.leon/config.env`：

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=claude-sonnet-4-5-20250929
```

这些就足够开始使用 Mycel 了。以下章节涵盖高级配置。

## 配置文件位置

Mycel 有三个独立的配置域，各自有对应的文件：

| 域 | 文件名 | 用途 |
|--------|----------|---------|
| 运行时行为 | `runtime.json` | 工具、记忆、MCP、技能、安全 |
| 模型身份 | `models.json` | 提供商、API 密钥、虚拟模型映射 |
| 可观测性 | `observation.json` | Langfuse / LangSmith 追踪 |
| 快速设置 | `config.env` | API 密钥 + Base URL（加载为环境变量） |
| 沙箱 | `~/.leon/sandboxes/<name>.json` | 每个沙箱提供商的配置 |

每个 JSON 配置文件从三个层级加载（优先级从高到低）：

1. **项目配置**：工作区根目录下的 `.leon/<file>`
2. **用户配置**：主目录下的 `~/.leon/<file>`
3. **系统默认值**：`config/defaults/` 中的内置默认值

CLI 参数（`--model`、`--workspace` 等）优先级最高，覆盖一切。

### 合并策略

- **runtime / memory / tools**：所有层级深度合并（高优先级层的字段覆盖低优先级层）
- **mcp / skills**：查找合并（第一个定义它的层级生效，不合并）
- **system_prompt**：查找（项目 > 用户 > 系统）
- **providers / mapping**（models.json）：按键深度合并
- **pool**（models.json）：后者覆盖（不合并列表）
- **catalog / virtual_models**（models.json）：仅系统级，不可覆盖

## 运行时配置（runtime.json）

控制智能体行为、工具、记忆、MCP 和技能。模型/提供商身份**不在**此处配置（那是 `models.json` 的职责）。

完整结构及默认值（来自 `config/defaults/runtime.json`）：

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

> **注意：** 文件是扁平结构——没有 `"runtime"` 包装键。配置加载器在加载时会内部包装这些字段。`spill_buffer`、`tool_modes`、`workspace_root` 等字段是可选覆盖项，不在默认文件中；详见下方[工具](#工具)章节。

### 运行时字段

| 字段 | 类型 | 默认值 | 说明 |
|-------|------|---------|-------------|
| `temperature` | float (0-2) | null（模型默认） | 采样温度 |
| `max_tokens` | int | null（模型默认） | 最大输出 token 数 |
| `context_limit` | int | 0 | 上下文窗口限制（token 数）。0 = 从模型自动检测 |
| `enable_audit_log` | bool | true | 启用审计日志 |
| `allowed_extensions` | list | null | 限制文件访问的扩展名列表。null = 全部 |
| `block_dangerous_commands` | bool | true | 阻止危险的 shell 命令（如 rm -rf 等） |
| `block_network_commands` | bool | false | 阻止网络命令 |

### 记忆

**裁剪（Pruning）** 修剪旧的工具结果以节省上下文空间：

| 字段 | 默认值 | 说明 |
|-------|---------|-------------|
| `soft_trim_chars` | 3000 | 超过此长度的工具结果进行软修剪 |
| `hard_clear_threshold` | 10000 | 超过此长度的工具结果进行硬清除 |
| `protect_recent` | 3 | 保留最近 N 条工具消息不修剪 |
| `trim_tool_results` | true | 启用工具结果修剪 |

**压缩（Compaction）** 通过 LLM 总结旧的对话历史：

| 字段 | 默认值 | 说明 |
|-------|---------|-------------|
| `reserve_tokens` | 16384 | 为新消息预留的空间 |
| `keep_recent_tokens` | 20000 | 保留最近消息的原文 |
| `min_messages` | 20 | 触发压缩前的最少消息数 |

### 工具

每个工具组（filesystem、search、web、command）都有一个 `enabled` 标志和一个 `tools` 子对象。工具组和单个工具都必须启用，工具才可用。

可用工具及其配置名称：

| 配置名称 | UI/工具目录名称 | 组 |
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

**溢出缓冲区（Spill buffer）** 自动将大型工具输出写入临时文件，而不是内联到对话中。这是可选覆盖项，不在系统默认文件中：

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

**工具模式** 可以为每个工具设置为 `"inline"`（默认）或 `"deferred"`。同样是可选覆盖项，不在默认文件中：

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

### 示例：项目级 runtime.json

项目根目录下的 `.leon/runtime.json`：

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

## 模型配置（models.json）

控制使用哪个模型、提供商凭据和虚拟模型映射。

### 结构

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

### 提供商

为每个提供商定义 API 凭据。`active.provider` 字段决定使用哪个提供商的凭据：

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

### API 密钥解析顺序

Mycel 按以下顺序查找 API 密钥：
1. `models.json` 中当前提供商的 `api_key`
2. `models.json` 中任何有 `api_key` 的提供商
3. 环境变量：`ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > `OPENROUTER_API_KEY`

### 提供商自动检测

未明确设置 `provider` 时，Mycel 从环境变量自动检测：
- 设置了 `ANTHROPIC_API_KEY` -> provider = `anthropic`
- 设置了 `OPENAI_API_KEY` -> provider = `openai`
- 设置了 `OPENROUTER_API_KEY` -> provider = `openai`

### 自定义模型

通过 `pool.custom` 列表添加不在内置目录中的模型：

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

`based_on` 告诉 Mycel 使用哪个模型族进行分词器/上下文检测。`context_limit` 覆盖自动检测的上下文窗口大小。

## 虚拟模型

Mycel 提供四个虚拟模型别名（`leon:*`），映射到具体模型并带有预设参数：

| 虚拟名称 | 具体模型 | 提供商 | 额外参数 | 适用场景 |
|-------------|---------------|----------|--------|----------|
| `leon:mini` | claude-haiku-4-5-20250929 | anthropic | - | 快速、简单任务 |
| `leon:medium` | claude-sonnet-4-5-20250929 | anthropic | - | 均衡、日常工作 |
| `leon:large` | claude-opus-4-6 | anthropic | - | 复杂推理 |
| `leon:max` | claude-opus-4-6 | anthropic | temperature=0.0 | 最高精度 |

用法：

```bash
leonai --model leon:mini
leonai --model leon:large
```

或在 `~/.leon/models.json` 中：

```json
{
  "active": {
    "model": "leon:large"
  }
}
```

### 覆盖虚拟模型映射

你可以在用户或项目的 `models.json` 中将虚拟模型重新映射到不同的具体模型：

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

当你只覆盖 `model` 而不指定 `provider` 时，继承的提供商会被清除（如果与自动检测不同，需要重新指定）。

## 智能体预设

Mycel 内置四个智能体预设，定义为带有 YAML frontmatter 的 Markdown 文件：

| 名称 | 说明 |
|------|-------------|
| `general` | 全功能通用智能体，默认子智能体 |
| `bash` | Shell 命令专家 |
| `explore` | 代码库探索与分析 |
| `plan` | 任务规划与分解 |

用法：

```bash
leonai --agent general
leonai --agent explore
```

### 智能体文件格式

智能体是带有 YAML frontmatter 的 `.md` 文件：

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

frontmatter 字段：

| 字段 | 必填 | 说明 |
|-------|----------|-------------|
| `name` | 是 | 智能体标识符 |
| `description` | 否 | 人类可读的说明 |
| `tools` | 否 | 工具白名单。`["*"]` = 所有工具（默认） |
| `model` | 否 | 此智能体的模型覆盖 |

### 智能体加载优先级

智能体从多个目录加载（后者按名称覆盖前者）：

1. 内置智能体：`config/defaults/agents/*.md`
2. 用户智能体：`~/.leon/agents/*.md`
3. 项目智能体：`.leon/agents/*.md`
4. 成员智能体：`~/.leon/members/<id>/agent.md`（最高优先级）

## 工具配置

完整的工具目录包含 runtime.json 配置组之外的工具：

| 工具 | 组 | 模式 | 说明 |
|------|-------|------|-------------|
| Read | filesystem | inline | 读取文件内容 |
| Write | filesystem | inline | 写入文件 |
| Edit | filesystem | inline | 编辑文件（精确替换） |
| list_dir | filesystem | inline | 列出目录内容 |
| Grep | search | inline | 正则搜索（基于 ripgrep） |
| Glob | search | inline | Glob 模式文件搜索 |
| Bash | command | inline | 执行 shell 命令 |
| WebSearch | web | inline | 互联网搜索 |
| WebFetch | web | inline | 获取网页并用 AI 提取内容 |
| Agent | agent | inline | 派生子智能体 |
| SendMessage | agent | inline | 向其他运行中智能体发送排队消息 |
| TaskOutput | agent | inline | 获取后台任务输出 |
| TaskStop | agent | inline | 停止后台任务 |
| TaskCreate | todo | deferred | 创建待办任务 |
| TaskGet | todo | deferred | 获取任务详情 |
| TaskList | todo | deferred | 列出所有任务 |
| TaskUpdate | todo | deferred | 更新任务状态 |
| load_skill | skills | inline | 加载技能 |
| tool_search | system | inline | 搜索可用工具 |

`deferred` 模式的工具异步运行，不会阻塞对话。

## MCP 配置

MCP 服务器在 `runtime.json` 的 `mcp` 键下配置。每个服务器可以使用 stdio（command + args）或 HTTP 传输（url）：

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

MCP 服务器字段：

| 字段 | 说明 |
|-------|-------------|
| `command` | 要启动的可执行文件（stdio 传输） |
| `args` | 命令参数 |
| `env` | 传递给服务器进程的环境变量 |
| `url` | 可流式 HTTP 传输的 URL（command 的替代方案） |
| `allowed_tools` | 工具名称白名单。null = 暴露所有工具 |

### 成员级 MCP

成员（`~/.leon/members/<id>/`）可以有自己的 `.mcp.json`，遵循与 Claude 的 MCP 配置相同的格式：

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

## 技能配置

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

技能路径是包含技能子目录的目录。每个技能有一个 `SKILL.md` 文件。`skills` 映射按名称启用/禁用单个技能。

技能路径必须在磁盘上存在——验证器要求 `paths` 中的每个目录都已创建。Mycel 不会自动创建它们。

## 可观测性配置（observation.json）

配置用于追踪智能体运行的可观测性提供商：

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

将 `active` 设置为 `"langfuse"`、`"langsmith"` 或 `null`（禁用）。

## 沙箱配置

沙箱配置位于 `~/.leon/sandboxes/<name>.json`。每个文件定义一个沙箱提供商：

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

支持的提供商：`local`、`docker`、`e2b`、`daytona`、`agentbay`。

启动时选择：

```bash
leonai --sandbox daytona       # 使用 ~/.leon/sandboxes/daytona.json
leonai --sandbox docker        # 使用 ~/.leon/sandboxes/docker.json
export LEON_SANDBOX=e2b        # 或通过环境变量设置
```

各提供商的特有字段：

| 提供商 | 字段 |
|----------|--------|
| docker | `image`、`mount_path`、`docker_host` |
| e2b | `api_key`、`template`、`cwd`、`timeout` |
| daytona | `api_key`、`api_url`、`target`、`cwd` |
| agentbay | `api_key`、`region_id`、`context_path`、`image_id` |

## 环境变量

### config.env 中的变量

`~/.leon/config.env` 是一个简单的 key=value 文件，在启动时加载为环境变量（仅在变量尚未设置时）：

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=claude-sonnet-4-5-20250929
```

`OPENAI_BASE_URL` 的值会自动规范化，缺少 `/v1` 时自动补齐。

### JSON 配置文件中的变量

`runtime.json`、`models.json` 和 `observation.json` 中的所有字符串值支持：

- `${VAR}` —— 环境变量展开
- `~` —— 主目录展开

```json
{
  "providers": {
    "anthropic": {
      "api_key": "${ANTHROPIC_API_KEY}"
    }
  }
}
```

### 相关环境变量

| 变量 | 用途 |
|----------|---------|
| `OPENAI_API_KEY` | API 密钥（OpenAI 兼容格式） |
| `OPENAI_BASE_URL` | API Base URL |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 |
| `ANTHROPIC_BASE_URL` | Anthropic Base URL |
| `OPENROUTER_API_KEY` | OpenRouter API 密钥 |
| `MODEL_NAME` | 覆盖模型名称 |
| `LEON_SANDBOX` | 默认沙箱名称 |
| `LEON_SANDBOX_DB_PATH` | 覆盖沙箱数据库路径 |
| `TAVILY_API_KEY` | Tavily 网络搜索 API 密钥 |
| `JINA_API_KEY` | Jina AI 抓取 API 密钥 |
| `EXA_API_KEY` | Exa 搜索 API 密钥 |
| `FIRECRAWL_API_KEY` | Firecrawl API 密钥 |
| `AGENTBAY_API_KEY` | AgentBay API 密钥 |
| `E2B_API_KEY` | E2B API 密钥 |
| `DAYTONA_API_KEY` | Daytona API 密钥 |

## CLI 参考

```bash
leonai                          # 启动新会话（TUI）
leonai -c                       # 继续上次会话
leonai --model leon:large       # 覆盖模型
leonai --agent explore          # 使用智能体预设
leonai --workspace /path        # 设置工作区根目录
leonai --sandbox docker         # 使用沙箱配置
leonai --thread <id>            # 恢复特定线程

leonai config                   # 交互式配置向导
leonai config show              # 显示当前 config.env

leonai thread ls                # 列出所有线程
leonai thread history <id>      # 显示线程历史
leonai thread rewind <id> <cp>  # 回退到检查点
leonai thread rm <id>           # 删除线程

leonai sandbox                  # 沙箱管理器 TUI
leonai sandbox ls               # 列出沙箱会话
leonai sandbox new [provider]   # 创建会话
leonai sandbox pause <id>       # 暂停会话
leonai sandbox resume <id>      # 恢复会话
leonai sandbox rm <id>          # 删除会话
leonai sandbox metrics <id>     # 显示资源指标

leonai run "message"            # 非交互式单条消息
leonai run --stdin              # 从标准输入读取消息
leonai run -i                   # 交互模式（无 TUI）
leonai run -d                   # 带调试输出
```
