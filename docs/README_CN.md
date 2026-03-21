# Mycel

<div align="center">

<img src="../assets/banner.png" alt="Mycel Banner" width="600">

**企业级 Agent 运行时，构建、运行和治理协作 AI 团队**

[🇬🇧 English](../README.md) | 🇨🇳 中文

[![PyPI version](https://badge.fury.io/py/leonai.svg)](https://badge.fury.io/py/leonai)
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

### 安装

```bash
pip install leonai
```

或使用 uv（推荐）：

```bash
uv tool install leonai
```

### 首次运行

```bash
leonai
```

首次启动时，Mycel 会引导您完成配置。您需要一个 OpenAI 兼容的 API 密钥。

### 最小配置

创建 `~/.leon/config.json`：

```json
{
  "api": {
    "api_key": "${OPENAI_API_KEY}",
    "model": "leon:balanced"
  }
}
```

### 第一次对话

```bash
leonai
```

```
你：当前目录有哪些文件？
Agent：[使用 list_dir 工具]
找到 12 个文件：README.md, pyproject.toml, src/, tests/, ...

你：读取 README 并总结
Agent：[使用 read_file 工具]
这个项目是...
```

## 核心概念

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

**支持的提供商**：
- **Local**：直接主机访问（开发）
- **Docker**：容器化隔离（测试）
- **E2B**：云沙箱（生产）
- **AgentBay**：阿里云（中国区域）

### 配置系统

三层配置合并：

```
系统默认 → 用户配置 → 项目配置 → CLI 参数
```

**虚拟模型**：
```bash
leonai --model leon:fast       # Sonnet, temp=0.7
leonai --model leon:balanced   # Sonnet, temp=0.5
leonai --model leon:powerful   # Opus, temp=0.3
leonai --model leon:coding     # Opus, temp=0.0
```

### Agent 预设

```bash
leonai --agent coder        # 代码开发
leonai --agent researcher   # 研究分析（只读）
leonai --agent tester       # QA 测试
```

## 功能特性

### TUI 界面

现代化终端界面，支持快捷键：

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 发送消息 |
| `Shift+Enter` | 换行 |
| `Ctrl+↑/↓` | 浏览历史 |
| `Ctrl+Y` | 复制最后消息 |
| `Ctrl+E` | 导出对话 |
| `Ctrl+L` | 清空历史 |
| `Ctrl+T` | 切换对话 |
| `ESC ESC` | 历史浏览器 |

### Web 界面

全功能 Web 界面：

```bash
leonai web
# 打开 http://localhost:8000
```

**功能**：
- 多 Agent 实时聊天
- 沙箱资源仪表板
- Token 使用和成本追踪
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

### 文件上传与工作区同步

上传文件到 Agent 工作区并同步更改（[PR #130](https://github.com/OpenDCAI/leonai/pull/130)）：

```bash
# 通过 Web UI 上传文件
# 文件在沙箱重启后持久化
```

**使用场景**：
- 上传数据集进行分析
- 与 Agent 共享代码文件
- 持久化配置文件
- 下载 Agent 生成的产物

### MCP 集成

连接外部服务：

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

### Skills 系统

按需加载专业技能：

```bash
你：加载代码审查技能
Agent：技能已加载。我现在可以执行详细的代码审查。
```

### 多沙箱支持

| 提供商 | 使用场景 | 成本 |
|--------|----------|------|
| **Local** | 开发 | 免费 |
| **Docker** | 测试 | 免费 |
| **E2B** | 生产 | $0.15/小时 |
| **AgentBay** | 中国区域 | ¥1/小时 |

```bash
leonai --sandbox docker
leonai sandbox ls
leonai sandbox pause <id>
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

## 路线图

**已完成** ✓
- 配置系统、TUI、MCP、Skills
- 多提供商沙箱
- Web 界面与仪表板
- 文件上传/下载（[PR #130](https://github.com/OpenDCAI/leonai/pull/130)）
- 多 Agent 通讯（Entity-Chat）

**进行中** 🚧
- Hook 系统、插件生态
- Agent 评估

## 文档

- [快速入门](getting-started.md) — 安装、LLM 配置、首次运行
- [配置指南](config/configuration.md) — 配置文件、虚拟模型、工具设置
- [多 Agent 通讯](multi-agent-chat.md) — Entity-Chat 系统、Agent 间通讯
- [沙箱](sandbox/SANDBOX.md) — 提供商、生命周期、会话管理
- [部署](deployment/DEPLOYMENT.md) — 生产部署指南
- [核心概念](product-primitives.md) — 核心抽象（Thread、Member、Task、Resource）
- [故障排查](TROUBLESHOOTING.md) — 常见问题与解决

## 贡献

```bash
git clone https://github.com/OpenDCAI/leonai.git
cd leonai
uv sync
uv run pytest
```

详见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

## 许可证

MIT License
