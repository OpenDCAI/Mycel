# P5: Agent 实例持久化 + SSE 事件清理

## 背景

当前 AgentPool（`backend/web/services/agent_pool.py`）是一个纯内存 dict，key 为 `thread_id:sandbox_type`，值为 LeonAgent 实例。进程重启后 pool 清空，agent 实例被重建但没有延续性。

SSE 事件流中使用硬编码字符串 `"main"` 标识主 Agent，用 `task_id` 标识子 Agent。后端和前端通过 `agent_id !== "main"` 来路由事件，这是一个设计缺陷。

Leon 的层次模型应该是 **member → agent → thread → run**，其中 agent 层缺失持久化身份。

## 为什么要改

### 1. `"main"` 是个假 ID

`"main"` 不是真实的身份标识，它是一个路由哨兵值。它把两个不同的关注点混在一起：

- **身份**（WHO）：这个 agent 是谁
- **路由**（WHERE）：这个事件该发到哪里

### 2. Agent ID 不属于事件数据

通过提问推导出的关键认知：

**Thread 是聊天的主体，Agent 是幕后执行者。** 事件属于 Thread 的上下文，不属于 Agent。用户连接的是 `/api/threads/{thread_id}/events`，不是 `/api/agents/{agent_id}/events`。

因此 `agent_id` 不应该出现在 SSE 事件数据中。它是后端内部的生命周期管理概念，不需要泄漏到传输协议层。

### 3. 路由应该用关系字段，不是身份字段

当前后端 drain 循环用 `agent_id != "main"` 区分主/子 agent 事件。但事件数据中已经有一个天然的关系字段——`parent_tool_call_id`：

- **有 `parent_tool_call_id`** → 这是某个 tool call 派生出来的子 agent 事件
- **没有** → 这是主 thread 的事件

这个字段表达的是事件的**来源关系**，比用身份字段做路由更准确。

## 推导过程

```
观察: agent_pool 是内存 dict，agent 没有持久化 ID
  ↓
想法: 给 agent 加持久化 UUID，替代 "main"
  ↓
追问: 主 agent leon 要不要存？
  → leon 是内置 member，和其他 member 一样，应该有 ID
  ↓
追问: 前端怎么区分主/子 agent？用 agent_id？
  → 不该用 ID 区分类型，应该用 type 字段
  ↓
追问: 子 agent 有自己的接口和路径，为什么要在事件里区分？
  → 路由在接口层（endpoint）已经天然分离，事件数据里不需要 type
  ↓
追问: 那事件里需要 agent_id 吗？
  → 不需要。Thread 是聊天主体，事件属于 Thread。
  → Agent 是执行者，不直接触发事件。
  → agent_id 是后端内部概念，不泄漏到 SSE 协议。
  ↓
结论:
  1. agent_instances.json 持久化 agent 身份（后端内部）
  2. SSE 事件移除 agent_id，用 parent_tool_call_id 做路由
  3. 前端去掉 "main" 判断，改用 parent_tool_call_id / background
```

## 设计

### S1. agent_instances.json — 后端内部持久化

**位置**：`~/.leon/agent_instances.json`

**结构**：
```json
{
  "a3f8c2": {
    "member": "leon",
    "thread_id": "uuid-xxx",
    "sandbox_type": "local",
    "created_at": 1741100000
  },
  "b5d9e1": {
    "member": "小专",
    "member_path": "~/.leon/members/小专",
    "thread_id": "uuid-yyy",
    "sandbox_type": "local",
    "created_at": 1741200000
  }
}
```

- key = `agent_id`（UUID 短 ID）
- 所有 agent 实例都存，包括内置 leon
- `get_or_create_agent` 命中时复用已有 agent_id，miss 时新建
- LeonAgent 实例增加 `agent_id` 属性

### S2. SSE 事件清理 — 移除 agent_id

**后端 emit 改造**：

`streaming_service.py:360`：
- 删除 `data["agent_id"] = "main"`

`core/task/subagent.py`（3 处）+ `core/command/middleware.py`（2 处）：
- 移除事件数据中的 `"agent_id": "main"`
- 后台任务事件保留 `"background": true`（用于前端 use-background-tasks 过滤）

**后端 drain 循环路由改造**：

`streaming_service.py:619-662`：
- 原：`agent_id != "main"` → 子 agent 事件
- 改：`parent_tool_call_id` 存在 → 子 agent 事件
- `task_start/task_done/task_error` 中有 `parent_tool_call_id` → 子 agent 生命周期
- `task_start/task_done/task_error` 中无 `parent_tool_call_id` 但有 `background: true` → 后台任务通知

### S3. 前端清理 — 去掉 "main"

`hooks/stream-event-handlers.ts:161,167`：
- 原：`agentId && agentId !== "main"` → handleSubagentEvent
- 改：`data.parent_tool_call_id` 存在 → handleSubagentEvent

`hooks/use-background-tasks.ts:46`：
- 原：`data?.background === true && data?.agent_id === "main"`
- 改：`data?.background === true && !data?.parent_tool_call_id`

### S4. Runtime 清理

`core/monitor/runtime.py`：
- `emit_subagent_event` 不再注入 `agent_id` 到事件数据（保留 `parent_tool_call_id` 和 `background`）
- `emit_activity_event` 无变化（本就不注入 agent_id）

## 涉及文件

| 文件 | 改动 | 步骤 |
|------|------|------|
| `~/.leon/agent_instances.json` | 新增 | S1 |
| `backend/web/services/agent_pool.py` | 读写 JSON，agent_id 赋值 | S1 |
| `agent.py` | LeonAgent 增加 agent_id 属性 | S1 |
| `backend/web/services/streaming_service.py` | 移除 `"main"` 注入，改路由逻辑 | S2 |
| `core/monitor/runtime.py` | emit_subagent_event 不注入 agent_id | S2/S4 |
| `core/task/subagent.py` | 3 处移除 `"agent_id": "main"` | S2 |
| `core/command/middleware.py` | 2 处移除 `"agent_id": "main"` | S2 |
| `frontend/.../stream-event-handlers.ts` | 改路由条件 | S3 |
| `frontend/.../use-background-tasks.ts` | 改过滤条件 | S3 |
| `frontend/.../subagent-event-handler.ts` | 移除 agent_id 相关逻辑 | S3 |
| `frontend/.../api/types.ts` | ContentEventData 移除 agent_id | S3 |

## 验证方案

1. 发送消息 → SSE 事件中无 `agent_id` 字段
2. 触发子 Agent → 事件通过 `parent_tool_call_id` 正确路由到子 agent buffer
3. 后台 bash 命令 → `task_start` 事件有 `background: true`，无 `agent_id`，前端正确更新
4. 重启后端 → `agent_instances.json` 中的 agent_id 不变
5. 前端代码中搜索 `"main"` → 0 结果（与 agent_id 路由相关的）

## 不在本 Plan 范围

- member 跨 thread 共享 agent 实例 → 留给 Agent 协作调度
- agent_instances.json 的 GC（清理已删除 thread 的条目）→ 可复用 thread 删除逻辑
- 前端展示 agent 身份信息 → 另建 UI 需求
