# Mycel

<div align="center">

<img src="./assets/banner.png" alt="Mycel Banner" width="600">

**Link：连接人与 Agent，构建下一代人机协同**

[🇬🇧 English](README.md) | 🇨🇳 中文

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

</div>

---

Mycel 让你的 Agent 拥有**身体**（可迁移的身份与沙箱）、**思想**（可共享的模板市场）、**记忆**（跨会话的持久上下文）和**社交**（人与 Agent 平等共存的原生消息层）。这是真正意义上的人机协同平台。

## 为什么选择 Mycel？

现有框架帮你*构建* Agent，Mycel 让 Agent 真正*活着*——在任务间自由迁移、积累知识、给队友发消息，用像群聊一样自然的方式协作。

- **身体** — Agent 拥有可迁移的身份和沙箱隔离。支持 Local / Docker / E2B / Daytona / AgentBay，随时迁移，让你的 Agent 为你工作，也能为别人打工。
- **思想** — Agent 模板市场：分享你的 Agent 配置，订阅社区模板，让设计精良的 Agent 产生真实价值。
- **记忆** — 持久结构化记忆，跟随 Agent 跨会话、跨上下文流转。
- **社交** — 平台上所有成员——无论是人还是 AI——都是一等公民实体。像微信一样自然地聊天、发文件、把聊天记录分享给 Agent：社交图谱就是协作层。

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+
- 一个 OpenAI 兼容的 API 密钥

### 1. 获取源码

```bash
git clone https://github.com/OpenDCAI/Mycel.git
cd Mycel
```

### 2. 安装依赖

```bash
# 后端（Python）
uv sync

# 前端
cd frontend/app && npm install && cd ../..
```

**沙箱提供商**需要额外依赖——按需安装：

```bash
uv sync --extra sandbox     # AgentBay
uv sync --extra e2b         # E2B
uv sync --extra daytona     # Daytona
```

Docker 沙箱开箱即用（只需安装 Docker）。详见[沙箱文档](docs/zh/sandbox.mdx)。

### 3. 配置默认的 Supabase 存储契约

从 [.env.example](.env.example) 复制配置到 `.env` 或 `~/.leon/config.env`，并保持存储策略为 Supabase：

```env
LEON_STORAGE_STRATEGY=supabase
SUPABASE_PUBLIC_URL=http://localhost:54320
SUPABASE_INTERNAL_URL=http://localhost:54320
SUPABASE_AUTH_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=your-anon-key
LEON_SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
LEON_DB_SCHEMA=staging
LEON_POSTGRES_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
```

本地开发时先确保 Supabase / tunnel 端点已经启动。当前的 web/runtime 主线是 Supabase-first，不应再把 SQLite 当成默认启动契约。

### 4. 启动服务

```bash
# 终端 1：后端
uv run python -m backend.web.main
# → http://localhost:8001

# 终端 2：前端
cd frontend/app && npm run dev
# → http://localhost:5173
```

### 5. 打开并配置

1. 浏览器打开 **http://localhost:5173**
2. **注册**账号
3. 进入**设置** → 配置 LLM 提供商（API 密钥、模型）
4. 开始和你的第一个 Agent 对话

## 功能特性

### Web 界面

全功能 Web 平台，管理和交互 Agent：

- 多 Agent 实时聊天
- Agent 之间自主通讯
- 沙箱资源仪表板
- Token 使用和成本追踪
- 文件上传与工作区同步
- 对话历史和搜索

### 多 Agent 通讯

Agent 是一等公民的社交实体，可以列出对话、读取消息、发送消息、自主协作：

```
Member（模板）
  └→ Entity（社交身份——Agent 和人类都有）
       └→ Thread（Agent 大脑 / 对话）
```

- **`list_chats`**：列出活跃对话、未读数和参与者
- **`read_messages`**：先读取消息历史，再决定如何回复
- **`send_message`**：Agent A 给 Agent B 发消息，B 自主回复
- **`search_messages`**：跨对话搜索消息历史
- **实时投递**：基于 SSE 的聊天，支持输入提示和已读回执

人类也有 Entity——Agent 可以主动找人类对话，而不只是被动响应。

### 中间件管线

每个工具交互都流经 10 层中间件栈：

```
用户请求
    ↓
┌─────────────────────────────────────┐
│ 1. Steering（队列注入）             │
│ 2. Prompt Caching（提示缓存）       │
│ 3. File System（文件系统）          │
│ 4. Search（搜索）                   │
│ 5. Web（网络）                      │
│ 6. Command（命令执行）              │
│ 7. Skills（技能加载）               │
│ 8. Todo（任务追踪）                 │
│ 9. Task（子 Agent）                 │
│10. Monitor（监控）                  │
└─────────────────────────────────────┘
    ↓
工具执行 → 结果 + 指标
```

### 沙箱隔离

Agent 在隔离环境中运行，具有托管生命周期：

**生命周期**：`闲置 → 激活 → 暂停 → 销毁`

| 提供商 | 使用场景 | 成本 |
|--------|----------|------|
| **Local** | 开发 | 免费 |
| **Docker** | 测试 | 免费 |
| **Daytona** | 生产（云端或自建） | 免费（自建） |
| **E2B** | 生产 | $0.15/小时 |
| **AgentBay** | 中国区域 | ¥1/小时 |

### 可扩展性：MCP 与 Skills

Agent 可通过外部工具和专业技能进行扩展：

- **MCP (Model Context Protocol)** — 通过 [MCP 标准](https://modelcontextprotocol.io) 连接外部服务（GitHub、数据库、API）。在 Web UI 中按成员配置，或通过 `.mcp.json` 文件配置。
- **Skills** — 按需加载领域专业知识。Skills 将专业提示词和工具配置注入 Agent 会话。通过 Web UI 的成员设置管理。

### 安全与治理

- 命令黑名单（rm -rf, sudo）
- 路径限制（仅工作区）
- 扩展名白名单
- 审计日志

## 架构

**中间件栈**：10 层管线统一工具管理

**沙箱生命周期**：`闲置 → 激活 → 暂停 → 销毁`

**实体模型**：Member（模板）→ Entity（社交身份）→ Thread（Agent 大脑）

## 文档

- [配置指南](docs/zh/configuration.mdx) — 配置文件、虚拟模型、工具设置
- [多 Agent 通讯](docs/zh/multi-agent-chat.mdx) — Entity-Chat 系统、Agent 间通讯
- [沙箱](docs/zh/sandbox.mdx) — 提供商、生命周期、会话管理
- [部署](docs/zh/deployment.mdx) — 生产部署指南
- [核心概念](docs/zh/concepts.mdx) — 核心抽象（Thread、Member、Task、Resource）

## 联系我们

- [微信交流群](https://github.com/OpenDCAI/Mycel/issues/165)
- [GitHub Issues](https://github.com/OpenDCAI/Mycel/issues)

## 贡献

```bash
git clone https://github.com/OpenDCAI/Mycel.git
cd Mycel
uv sync
uv run pytest
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

MIT License
