# Mycel

<div align="center">

<img src="./assets/banner.png" alt="Mycel Banner" width="600">

**企业级 Agent 运行时，构建、运行和治理协作 AI 团队**

[🇬🇧 English](README.md) | 🇨🇳 中文

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

</div>

---

Mycel 是企业级 Agent 运行时，将 AI Agent 视为长期运行的协作伙伴。基于中间件优先架构，提供现有 Agent 框架缺失的基础设施层：沙箱隔离、多 Agent 通讯和生产治理。

## 为什么选择 Mycel？

现有 Agent 框架专注于*构建* Agent，Mycel 专注于在生产环境*运行*它们：

- **中间件管线**：统一的工具注入、校验、安全和可观测性
- **沙箱隔离**：在 Docker/E2B/云端运行 Agent，自动状态管理
- **多 Agent 通讯**：Agent 之间互相发现、发送消息、自主协作——人类也参与其中
- **生产治理**：内置安全控制、审计日志和成本追踪

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

### 3. 启动服务

```bash
# 终端 1：后端
uv run python -m backend.web.main
# → http://localhost:8001

# 终端 2：前端
cd frontend/app && npm run dev
# → http://localhost:5173
```

### 4. 打开并配置

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

Agent 是一等公民的社交实体，可以互相发现、发送消息、自主协作：

```
Member（模板）
  └→ Entity（社交身份——Agent 和人类都有）
       └→ Thread（Agent 大脑 / 对话）
```

- **`chat_send`**：Agent A 给 Agent B 发消息，B 自主回复
- **`directory`**：Agent 浏览和发现其他实体
- **`tell_owner`**：Agent 向人类 Owner 上报
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
| **E2B** | 生产 | $0.15/小时 |
| **AgentBay** | 中国区域 | ¥1/小时 |

### MCP 集成

通过 [Model Context Protocol](https://modelcontextprotocol.io) 连接外部服务：

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

### 安全与治理

- 命令黑名单（rm -rf, sudo）
- 路径限制（仅工作区）
- 扩展名白名单
- 审计日志

## 架构

**中间件栈**：10 层管线统一工具管理

**沙箱生命周期**：`闲置 → 激活 → 暂停 → 销毁`

**实体模型**：Member（模板）→ Entity（社交身份）→ Thread（Agent 大脑）

**关系**：Member (1:N) → Thread (N:1) → Sandbox

## 文档

- [快速入门](docs/zh/getting-started.md) — 安装、LLM 配置、首次运行
- [配置指南](docs/zh/configuration.md) — 配置文件、虚拟模型、工具设置
- [多 Agent 通讯](docs/zh/multi-agent-chat.md) — Entity-Chat 系统、Agent 间通讯
- [沙箱](docs/zh/sandbox.md) — 提供商、生命周期、会话管理
- [部署](docs/zh/deployment.md) — 生产部署指南
- [核心概念](docs/zh/product-primitives.md) — 核心抽象（Thread、Member、Task、Resource）

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
