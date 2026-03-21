[🇬🇧 English](../en/sandbox.md) | 🇨🇳 中文

# 沙箱

Mycel 的沙箱系统将 Agent 操作（文件 I/O、Shell 命令）运行在隔离环境中，而非宿主机上。支持 5 种 Provider：**Local**（主机直通）、**Docker**（容器）、**E2B**（云端）、**Daytona**（云端或自建）、**AgentBay**（阿里云）。

## 快速开始（Web UI）

### 1. 配置 Provider

在 Web UI 中进入 **设置 → 沙箱**。你会看到每个 Provider 的配置卡片，展开后填写必要字段：

| Provider | 必填字段 |
|----------|---------|
| **Docker** | 镜像名（默认 `python:3.12-slim`）、挂载路径 |
| **E2B** | API 密钥 |
| **Daytona** | API 密钥、API URL |
| **AgentBay** | API 密钥 |

点击 **保存**。配置存储在 `~/.leon/sandboxes/<provider>.json`。

### 2. 创建使用沙箱的对话

开始新对话时，在输入框左上角的**沙箱下拉菜单**中选择已配置的 Provider（如 `docker`）。然后输入消息并发送。

对话在创建时绑定到该沙箱——后续所有 Agent 运行都使用同一个沙箱。

### 3. 监控资源

进入侧边栏的**资源**页面，你会看到：

- **Provider 卡片** — 每个 Provider 的状态（活跃/就绪/不可用）
- **沙箱卡片** — 每个运行中/暂停的沙箱，包含 Agent 头像、持续时间和指标（CPU/RAM/Disk）
- **详情面板** — 点击沙箱卡片查看使用它的 Agent、详细指标和文件浏览器

## Provider 配置

### Docker

需要主机安装 Docker。无需 API 密钥。

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
| `docker.image` | `python:3.12-slim` | Docker 镜像 |
| `docker.mount_path` | `/workspace` | 容器内工作目录 |
| `on_exit` | `pause` | `pause`（保留状态）或 `destroy`（清空重来） |

### E2B

云端沙箱服务。需要 [E2B](https://e2b.dev) API 密钥。

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

支持 [Daytona](https://daytona.io) SaaS 和自建实例。

**SaaS：**
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

**自建：**
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

阿里云沙箱（中国区域）。需要 AgentBay API 密钥。

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

### 额外依赖

云端沙箱 Provider 需要额外 Python 包：

```bash
uv sync --extra sandbox     # AgentBay
uv sync --extra e2b         # E2B
uv sync --extra daytona     # Daytona
```

Docker 开箱即用（使用 Docker CLI）。

### API 密钥解析

API 密钥按以下顺序查找：

1. 配置文件字段（`e2b.api_key`、`daytona.api_key` 等）
2. 环境变量（`E2B_API_KEY`、`DAYTONA_API_KEY`、`AGENTBAY_API_KEY`）
3. `~/.leon/config.env`

## 会话生命周期

每个对话绑定一个沙箱。会话遵循生命周期：

```
闲置 → 激活 → 暂停 → 销毁
```

### `on_exit` 行为

| 值 | 行为 |
|----|------|
| `pause` | 退出时暂停会话。下次启动恢复。文件、安装的包、进程都保留。 |
| `destroy` | 退出时销毁会话。下次从零开始。 |

`pause` 是默认值——跨重启保留所有状态。

### Web UI 会话管理

在**资源**页面：

- 统一网格视图查看所有 Provider 的所有会话
- 点击会话卡片 → 详情面板，包含指标和文件浏览器
- 通过 API 暂停 / 恢复 / 销毁

**API 端点：**

| 操作 | 端点 |
|------|------|
| 查看资源 | `GET /api/monitor/resources` |
| 强制刷新 | `POST /api/monitor/resources/refresh` |
| 暂停会话 | `POST /api/sandbox/sessions/{id}/pause?provider={type}` |
| 恢复会话 | `POST /api/sandbox/sessions/{id}/resume?provider={type}` |
| 销毁会话 | `DELETE /api/sandbox/sessions/{id}?provider={type}` |

## CLI 参考

终端下的沙箱管理请见 [CLI 文档](cli.md#沙箱管理)。

命令摘要：

```bash
leonai sandbox              # TUI 管理器
leonai sandbox ls           # 列出会话
leonai sandbox new docker   # 创建会话
leonai sandbox pause <id>   # 暂停
leonai sandbox resume <id>  # 恢复
leonai sandbox rm <id>      # 删除
leonai sandbox metrics <id> # 查看指标
```

## 架构

沙箱是中间件栈下方的基础设施层。它提供后端供现有中间件使用：

```
Agent
  ├── sandbox.fs()    → FileSystemBackend（FileSystemMiddleware 使用）
  └── sandbox.shell() → BaseExecutor（CommandMiddleware 使用）
```

中间件负责**策略**（校验、路径规则、hook）。后端负责**I/O**（操作实际执行位置）。切换后端改变执行位置而不影响中间件逻辑。

### 会话追踪

会话记录在 SQLite（`~/.leon/sandbox.db`）中：

| 表 | 用途 |
|----|------|
| `sandbox_leases` | Lease 生命周期 — Provider、期望/观测状态 |
| `sandbox_instances` | Provider 侧的会话 ID |
| `abstract_terminals` | 绑定到 Thread + Lease 的虚拟终端 |
| `lease_resource_snapshots` | CPU、内存、磁盘指标 |

Thread → 沙箱的映射通过 `abstract_terminals.thread_id` → `abstract_terminals.lease_id`。
