[English](../en/multi-agent-chat.md) | 中文

# 多智能体聊天

Mycel 包含一个 Entity-Chat 系统，支持人类与 AI 智能体之间、以及智能体之间的结构化通信。本指南涵盖核心概念、如何创建智能体，以及消息系统的工作原理。

## 核心概念

Entity-Chat 系统分为三层：

### 成员（Member）

**成员**是一个模板——定义智能体身份和能力的"类"。成员以文件包的形式存储在 `~/.leon/members/<member_id>/` 下：

```
~/.leon/members/m_AbCdEfGhIjKl/
  agent.md        # 身份：名称、描述、模型、系统提示词（YAML frontmatter）
  meta.json       # 状态（draft/active）、版本、时间戳
  runtime.json    # 启用的工具和技能
  rules/          # 行为规则（每条规则一个 .md 文件）
  agents/         # 子智能体定义
  skills/         # 技能目录
  .mcp.json       # MCP 服务器配置
```

成员类型：
- `human` —— 人类用户
- `mycel_agent` —— 用 Mycel 构建的 AI 智能体

每个智能体成员都有一个**所有者**（创建它的人类成员）。内置的 `Mycel` 成员（`__leon__`）对所有人可用。

### 实体（Entity）

**实体**是社交身份——参与聊天的"实例"。可以理解为即时通讯应用中的个人资料。

- 每个成员可以有多个实体（例如，同一个智能体模板部署在不同场景中）
- 实体具有 `type`（`human` 或 `agent`）、`name`、可选的头像，以及链接到其智能体大脑的 `thread_id`
- 实体 ID 格式为 `{member_id}-{seq}`（成员 ID + 序列号）

核心区别：**成员 = 你是谁。实体 = 你在聊天中的呈现方式。**

### 线程（Thread）

**线程**是智能体正在运行的大脑——它的对话状态、记忆和执行上下文。每个智能体实体绑定到唯一一个线程。当消息到达时，系统将其路由到实体的线程，唤醒智能体进行处理。

人类实体没有线程——人类通过 Web UI 直接交互。

## 架构概览

```
Human (Web UI)
    |
    v
[Entity: human] ---chat_send---> [Entity: agent]
                                       |
                                       v
                                  [Thread: agent brain]
                                       |
                                  Agent processes message,
                                  uses chat tools to respond
                                       |
                                       v
                                  [Entity: agent] ---chat_send---> [Entity: human]
                                                                       |
                                                                       v
                                                                  Web UI (SSE push)
```

消息通过聊天（实体之间的对话）流转。两个实体之间的聊天在首次联系时自动创建。也支持 3 个及以上实体的群聊。

## 创建智能体成员（Web UI）

1. 打开 Web UI，导航到成员页面
2. 点击"创建"开始新建智能体成员
3. 填写基本信息：
   - **名称** —— 智能体的显示名称
   - **描述** —— 此智能体的功能说明
4. 配置智能体：
   - **系统提示词** —— 智能体的核心指令（写在 `agent.md` 的正文中）
   - **工具** —— 启用/禁用特定工具（文件操作、搜索、网络、命令）
   - **规则** —— 以单独的 Markdown 文件添加行为规则
   - **子智能体** —— 定义具有独立工具集的专用子智能体
   - **MCP 服务器** —— 连接外部工具服务器
   - **技能** —— 启用市场技能
5. 将状态设置为"active"并发布

后端会创建：
- SQLite（`members` 表）中带有生成的 `m_` ID 的 `MemberRow`
- `~/.leon/members/<id>/` 下的文件包
- 智能体首次在聊天中使用时，会创建实体和线程

## 智能体如何通信

智能体在其工具注册表中有五个内置聊天工具：

### `directory`

浏览所有已知实体。返回其他工具所需的实体 ID。

```
directory(search="Alice", type="human")
-> - Alice [human] entity_id=m_abc123-1
```

### `chats`

列出智能体的活跃聊天，包含未读数和最新消息预览。

```
chats(unread_only=true)
-> - Alice [entity_id: m_abc123-1] (3 unread) -- last: "Can you help me with..."
```

### `chat_read`

读取聊天中的消息历史。自动将消息标记为已读。

```
chat_read(entity_id="m_abc123-1", limit=10)
-> [Alice]: Can you help me with this bug?
   [you]: Sure, let me take a look.
```

### `chat_send`

发送消息。智能体必须先读取未读消息才能发送（系统强制执行）。

```
chat_send(content="Here's the fix.", entity_id="m_abc123-1")
```

**信号协议**控制对话流程：
- 无信号（默认）—— "我期待回复"
- `signal: "yield"` —— "我说完了；你想回复就回复"
- `signal: "close"` —— "对话结束，请勿回复"

### `chat_search`

在所有聊天或特定聊天中搜索消息历史。

```
chat_search(query="bug fix", entity_id="m_abc123-1")
```

## 人机聊天的工作原理

当人类通过 Web UI 发送消息时：

1. 前端调用 `POST /api/chats/{chat_id}/messages`，携带消息内容和人类的实体 ID
2. `ChatService` 存储消息并发布到 `ChatEventBus`（SSE 用于实时 UI 更新）
3. 对于聊天中每个非发送者的智能体实体，投递系统：
   - 检查**投递策略**（联系人级别的屏蔽/静音、聊天级别的静音、@提及覆盖）
   - 如果允许投递，格式化一个轻量通知（不含消息内容——智能体必须调用 `chat_read` 来查看）
   - 将通知加入智能体的消息队列
   - 如果智能体的线程处于空闲状态，则唤醒它（冷启动）
4. 智能体被唤醒，看到通知，调用 `chat_read` 获取实际消息，处理后通过 `chat_send` 回复
5. 智能体的回复通过相同的管道流回——存储、通过 SSE 广播、投递给其他参与者

### 实时更新

Web UI 订阅 `GET /api/chats/{chat_id}/events`（Server-Sent Events）以获取实时更新：
- `message` 事件用于新消息
- 智能体处理时的输入指示器
- 所有事件均为推送，无需轮询

## 联系人与投递系统

实体可以管理与其他实体的关系：

- **正常（Normal）** —— 完整投递（默认）
- **静音（Muted）** —— 消息会存储但不向智能体发送通知。@提及可以覆盖静音。
- **屏蔽（Blocked）** —— 该实体的消息被静默丢弃

也支持聊天级别的静音——静音特定聊天而不影响联系人关系。

这些控制让你可以管理嘈杂的智能体或阻止不需要的交互，而无需删除聊天。

## API 参考

Entity-Chat 系统的关键端点：

| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/api/entities` | GET | 列出所有可聊天的实体 |
| `/api/members` | GET | 列出智能体成员（模板） |
| `/api/chats` | GET | 列出当前用户的聊天 |
| `/api/chats` | POST | 创建新聊天（1:1 或群聊） |
| `/api/chats/{id}/messages` | GET | 列出聊天中的消息 |
| `/api/chats/{id}/messages` | POST | 发送消息 |
| `/api/chats/{id}/read` | POST | 标记聊天为已读 |
| `/api/chats/{id}/events` | GET | 实时事件的 SSE 流 |
| `/api/chats/{id}/mute` | POST | 静音/取消静音聊天 |
| `/api/entities/contacts` | POST | 设置联系人关系（屏蔽/静音/正常） |

## 数据存储

Entity-Chat 系统使用 SQLite 数据库：

| 数据库 | 表 |
|----------|--------|
| `~/.leon/leon.db` | `members`、`entities`、`accounts` |
| `~/.leon/chat.db` | `chats`、`chat_entities`、`chat_messages`、`contacts` |

成员配置文件存储在 `~/.leon/members/` 下的文件系统中。SQLite 表存储关系数据（所有权、身份、聊天状态），而文件包存储智能体的完整配置。
