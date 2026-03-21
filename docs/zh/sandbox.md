# Sandbox

[English](../en/sandbox.md) | 中文

LEON 的 Sandbox 系统将 Agent 操作（文件 I/O、Shell 命令）运行在隔离环境中，而非宿主机上。支持四种 Provider：**Docker**（本地容器）、**E2B**（云端）、**Daytona**（云端或自托管）和 **AgentBay**（阿里云）。

## 快速开始

```bash
# 在 Docker 容器中运行 LEON
leonai --sandbox docker

# 在 E2B 云端沙盒中运行 LEON
leonai --sandbox e2b

# 在 Daytona 云端沙盒中运行 LEON
leonai --sandbox daytona

# 在 AgentBay 云端沙盒中运行 LEON
leonai --sandbox agentbay

# Headless 模式
leonai run --sandbox docker "List files in the workspace"

# 查看和管理 Sandbox 会话
leonai sandbox              # TUI 管理器
leonai sandbox ls           # 列出会话
leonai sandbox new docker   # 创建会话
leonai sandbox pause <id>   # 暂停会话
leonai sandbox resume <id>  # 恢复会话
leonai sandbox rm <id>      # 删除会话
leonai sandbox metrics <id> # 显示资源指标
leonai sandbox destroy-all-sessions  # 销毁所有会话
```

## 配置

### 配置文件

每个 Sandbox Provider 通过 `~/.leon/sandboxes/` 下的 JSON 文件配置：

```
~/.leon/sandboxes/
├── docker.json
├── e2b.json
├── daytona.json
└── agentbay.json
```

文件名（去掉 `.json`）即为传给 `--sandbox` 的名称。

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

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `docker.image` | `python:3.12-slim` | 使用的 Docker 镜像 |
| `docker.mount_path` | `/workspace` | 容器内的工作目录 |
| `on_exit` | `pause` | Agent 退出时的行为：`pause` 或 `destroy` |

**前置要求：** 宿主机上需要有 Docker CLI。

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

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `e2b.api_key` | — | E2B API key（或设置 `E2B_API_KEY` 环境变量） |
| `e2b.template` | `base` | E2B 沙盒模板 |
| `e2b.cwd` | `/home/user` | 工作目录 |
| `e2b.timeout` | `300` | 会话超时时间（秒） |
| `on_exit` | `pause` | `pause` 或 `destroy` |

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

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `daytona.api_key` | — | Daytona API key（或设置 `DAYTONA_API_KEY` 环境变量） |
| `daytona.api_url` | `https://app.daytona.io/api` | Daytona API 基础 URL |
| `daytona.cwd` | `/home/daytona` | 工作目录 |
| `on_exit` | `pause` | `pause` 或 `destroy` |

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

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `agentbay.api_key` | — | AgentBay API key（或设置 `AGENTBAY_API_KEY` 环境变量） |
| `agentbay.region_id` | `ap-southeast-1` | 云区域 |
| `agentbay.context_path` | `/home/wuying` | 工作目录 |
| `agentbay.image_id` | `null` | 指定镜像（可选） |
| `on_exit` | `pause` | `pause` 或 `destroy` |

### API Key 解析顺序

API key 按以下顺序解析：

1. 配置文件字段（`e2b.api_key`、`agentbay.api_key`）
2. 环境变量（`E2B_API_KEY`、`AGENTBAY_API_KEY`）
3. `~/.leon/config.env`（自动加载）

在 `config.env` 中设置 key：

```bash
leonai config
# 或手动编辑 ~/.leon/config.env：
# AGENTBAY_API_KEY=akm-...
# E2B_API_KEY=e2b_...
```

### Sandbox 名称解析顺序

Sandbox 名称按以下顺序解析：

1. CLI 参数：`leonai --sandbox docker`
2. 自动检测：恢复线程（`--thread` 或 `-c`）时，系统从 SQLite 中查找 Provider
3. 环境变量：`LEON_SANDBOX=docker`
4. 默认值：`local`（无沙盒，直接在宿主机运行）

自动检测意味着恢复之前使用过沙盒的线程时，无需再次传 `--sandbox`。如果沙盒配置文件缺失或会话已销毁，将静默回退到本地模式。

## 会话生命周期

会话按对话线程管理：

```
线程 "abc" 中首次工具调用
  → 创建新的 Sandbox 会话
  → 在 SQLite 中映射 线程 "abc" → session_id

Agent 退出（on_exit="pause"）
  → 暂停所有运行中的会话
  → 会话保留，供下次启动使用

下次启动，同一线程
  → 恢复已暂停的会话
  → 状态完整（文件、已安装的包等）
```

### `on_exit` 行为

| 值 | 行为 |
|------|----------|
| `pause` | 退出时暂停会话。下次启动时恢复。状态保留。 |
| `destroy` | 退出时销毁会话。下次从零开始。 |

`pause` 是默认且推荐的开发模式 — 在 LEON 重启后保留已安装的包、创建的文件和运行中的进程。

## 会话管理

### CLI 命令

所有 TUI 操作也可通过 CLI 子命令使用：

```bash
# 列出所有 Provider 的所有会话
leonai sandbox ls

# 创建新会话（省略时使用第一个可用 Provider）
leonai sandbox new
leonai sandbox new docker
leonai sandbox new e2b

# 暂停 / 恢复 / 删除（接受会话 ID 前缀）
leonai sandbox pause iolzc
leonai sandbox resume iolzc
leonai sandbox rm iolzc

# 显示 CPU、内存、磁盘、网络指标
leonai sandbox metrics iolzc

# 销毁所有会话（需确认）
leonai sandbox destroy-all-sessions
```

会话 ID 可以缩写 — 任何唯一前缀都有效。

### TUI 管理器

```bash
leonai sandbox
```

打开全屏 TUI，交互式管理会话。

### 布局

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

### 快捷键

| 按键 | 操作 |
|------|------|
| `r` | 刷新会话列表 |
| `n` | 创建新会话（使用第一个可用 Provider） |
| `d` | 删除选中的会话 |
| `p` | 暂停选中的会话 |
| `u` | 恢复选中的会话 |
| `m` | 显示指标（CPU、内存、磁盘、网络） |
| `o` | 在浏览器中打开 Web URL（仅 AgentBay） |
| `q` | 退出 |

### Provider 发现

管理器从所有 `~/.leon/sandboxes/*.json` 配置文件中加载 Provider。如果某个 Provider 的 API key 缺失，该 Provider 将被静默跳过。所有可用 Provider 的会话显示在同一个统一表格中。

### 暂停/恢复支持

部分 Provider 或账户等级不支持暂停/恢复。当检测到此情况（通过 `BenefitLevel.NotSupport` 错误），该会话的暂停和恢复按钮将显示为 "(N/A)"。此状态按会话缓存。

### 指标

选中一个会话并按 `m` 显示：

## Daytona

`daytona` 同时支持 Daytona SaaS 和自托管 Daytona。这是纯配置差异：设置 `daytona.api_url` 即可。

- 默认（SaaS）：`daytona.api_url` 为 `https://app.daytona.io/api`
- 自托管：将 `daytona.api_url` 设为你自己的服务器（必须包含 `/api`，如 `https://daytona.example.com/api`）

示例 `~/.leon/sandboxes/daytona.json`（自托管）：
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

Web URL: https://...  (仅 AgentBay)
```

Docker 指标来自 `docker stats`。AgentBay 指标来自云端 API。E2B 不提供指标。

## 架构

### 工作原理

Sandbox 是 Middleware 栈**下方的基础设施层**。它不拥有工具 — 它提供现有 Middleware 使用的**后端**：

```
LeonAgent
  │
  ├── sandbox.fs()    → FileSystemBackend  (used by FileSystemMiddleware)
  └── sandbox.shell() → BaseExecutor       (used by CommandMiddleware)
```

Middleware 负责**策略**（Hooks、验证、路径规则）。Backend 负责 **I/O 机制**（操作实际在哪里执行）。切换 Backend 改变操作执行位置，而不影响 Middleware 逻辑。

`FileSystemBackend` 和 `BaseExecutor` 两个抽象基类都有 `is_remote` 属性（默认 `False`）。Sandbox Backend 设置 `is_remote = True`，Middleware 据此跳过仅适用于本地的逻辑（如 `Path.resolve()`、`mkdir`、Hooks）。

对于本地模式，`sandbox.fs()` 和 `sandbox.shell()` 返回 `None`，Middleware 回退到 `LocalBackend`（宿主机文件系统）和系统检测的 Shell（zsh/bash/powershell）。

Provider 命令结果使用 `ProviderExecResult`（sandbox/provider.py），由 `SandboxExecutor` 转换为 Middleware 的 `ExecuteResult`（middleware/command/base.py）。

### 文件结构

```
sandbox/
├── __init__.py          # 工厂：create_sandbox()
├── base.py              # 抽象 Sandbox 接口
├── config.py            # SandboxConfig、Provider 配置、DEFAULT_DB_PATH
├── capability.py        # Provider 能力检测
├── chat_session.py      # 聊天会话生命周期
├── lease.py             # Lease 状态机
├── lifecycle.py         # Sandbox 生命周期编排
├── manager.py           # SandboxManager（会话编排）
├── provider.py          # SandboxProvider ABC、ProviderExecResult、Metrics
├── provider_events.py   # Provider 事件处理
├── resource_snapshot.py # 资源指标快照
├── runtime.py           # 运行时环境
├── shell_output.py      # Shell 输出处理
├── terminal.py          # 抽象终端管理
├── thread_context.py    # ContextVar，用于 thread_id 追踪
└── providers/
    ├── agentbay.py      # AgentBayProvider（阿里云 SDK）
    ├── daytona.py       # DaytonaProvider（Daytona SDK，SaaS 或自托管）
    ├── docker.py        # DockerProvider（Docker CLI）
    ├── e2b.py           # E2BProvider（E2B SDK）
    └── local.py         # LocalProvider（宿主机直通）

middleware/
├── filesystem/
│   ├── backend.py           # FileSystemBackend ABC（is_remote 属性）
│   ├── local_backend.py     # LocalBackend（宿主机文件系统）
│   └── sandbox_backend.py   # SandboxFileBackend（is_remote=True）
└── command/
    ├── base.py              # BaseExecutor ABC（is_remote 属性）
    └── sandbox_executor.py  # SandboxExecutor（is_remote=True）
```

### 两层抽象

**Sandbox**（如 `DockerSandbox`）为给定环境捆绑了文件系统后端 + Shell 执行器 + 会话管理。

**Provider**（如 `DockerProvider`）是实际与 Docker CLI / E2B SDK / AgentBay SDK 通信的 API 客户端。

Sandbox 层处理会话缓存、线程上下文和生命周期。Provider 层处理原始 API 调用。

### 会话追踪

会话在 SQLite（`~/.leon/sandbox.db`）中通过多张表追踪：

| 表 | 用途 |
|------|---------|
| `sandbox_leases` | Lease 生命周期 — 每个沙盒环境一个 Lease。追踪 Provider、期望/实际状态、实例绑定。 |
| `sandbox_instances` | 绑定到 Lease 的 Provider 端会话 ID。 |
| `lease_events` | Lease 状态转换的审计日志。 |
| `abstract_terminals` | 绑定到线程 + Lease 的虚拟终端。追踪 cwd 和环境变量差异。 |
| `thread_terminal_pointers` | 将每个线程映射到其活跃和默认终端。 |
| `chat_sessions` | 关联线程、终端和 Lease 的对话会话，带有 TTL/预算。 |
| `terminal_commands` | 每个终端的命令历史（stdin、stdout、stderr、退出码）。 |
| `terminal_command_chunks` | 长时间运行命令的流式 stdout/stderr 块。 |
| `provider_events` | 从 Provider 接收的原始事件（用于状态对账）。 |
| `lease_resource_snapshots` | 每个 Lease 的 CPU、内存、磁盘指标（由资源监控器写入）。 |

线程到沙盒的映射通过 `abstract_terminals.thread_id` + `abstract_terminals.lease_id`（`sandbox_leases` 上没有 `thread_id` 列）。

独立的 `lookup_sandbox_for_thread()` 函数支持恢复线程时的沙盒自动检测 — 它做纯 SQLite 查询，无需初始化任何 Provider。

## Headless 测试

Sandbox 可以在无 TUI 的情况下进行端到端测试：

```bash
# 单条消息
leonai run --sandbox docker -d "Run echo hello"

# 交互式
leonai run --sandbox e2b -i

# 编程方式（Python）
from agent import create_leon_agent
agent = create_leon_agent(sandbox="docker")
result = agent.invoke("List files", thread_id="test-1")
agent.close()
```

完整测试套件见 `tests/test_sandbox_e2e.py`。
