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

### 3. 路由只需要两层：Thread + run_id

事件路由不需要额外字段：
- **Thread 级**：SSE 连接 URL 已确定归属（`/api/threads/{thread_id}/events`）
- **Turn 级**：`run_id`（`run_start` / `run_done` 标记边界）确定事件属于哪轮

子 Agent 不需要特殊路由：
- **Blocking**：就是正常的 tool_call → tool_result，自然属于当前 Turn
- **Async**：启动的 tool_call 已有 tool_result，之后异步任务属于整个 Thread，通过 `task_start` / `task_done` 通知

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
追问: 路由靠什么？parent_tool_call_id？
  → 不对。路由只有两层：Thread（SSE 连接）+ Turn（run_id）
  → Blocking 子 Agent = 正常 tool_call → tool_result，自然在当前 Turn
  → Async 子 Agent = 启动完就属于 Thread，走 task_start/task_done 通知
  → parent_tool_call_id 不是路由字段，最多作为元数据记录来源
  ↓
结论:
  1. agent_instances.json 持久化 agent 身份（后端内部）
  2. SSE 事件移除 agent_id，路由靠 SSE 连接 + run_id
  3. 前端去掉 "main" 判断，去掉 parent_tool_call_id 路由逻辑
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

**后端 drain 循环 — 删除 subagent buffer**：

`streaming_service.py:619-662`：
- 删除 subagent buffer 数据结构和所有基于 `agent_id != "main"` 的分流逻辑
- 所有事件统一走主 SSE 流，不再分流到 subagent buffer
- 子 Agent 执行细节通过 Task Output REST API 按需拉取（P3 已实现）

### S3. 前端清理

`hooks/stream-event-handlers.ts:161,167`：
- 删除 `agentId && agentId !== "main"` → handleSubagentEvent 的路由分支
- 删除 handleSubagentEvent 调用链
- task_start/task_done/task_error 作为普通事件处理

`hooks/use-background-tasks.ts:46`：
- 原：`data?.background === true && data?.agent_id === "main"`
- 改：`data?.background === true`

`hooks/subagent-event-handler.ts`：
- 不再被 SSE 路由调用，可以删除或保留给 REST API 用

`api/types.ts`：
- ContentEventData 移除 `agent_id` 字段

### S4. Runtime 清理

`core/monitor/runtime.py`：
- `emit_subagent_event` 移除 `agent_id` 参数，不再注入到事件数据
- `parent_tool_call_id` 保留为元数据（记录来源关系，不参与路由）
- `emit_activity_event` 无变化

## 涉及文件

| 文件 | 改动 | 步骤 |
|------|------|------|
| `~/.leon/agent_instances.json` | 新增 | S1 |
| `backend/web/services/agent_pool.py` | 读写 JSON，agent_id 赋值 | S1 |
| `agent.py` | LeonAgent 增加 agent_id 属性 | S1 |
| `backend/web/services/streaming_service.py` | 移除 `"main"` 注入，删除 subagent buffer | S2 |
| `core/monitor/runtime.py` | emit_subagent_event 移除 agent_id 参数 | S2/S4 |
| `core/task/subagent.py` | 移除 `"agent_id": "main"` | S2 |
| `core/command/middleware.py` | 移除 `"agent_id": "main"` | S2 |
| `frontend/.../stream-event-handlers.ts` | 删除 subagent 路由分支 | S3 |
| `frontend/.../use-background-tasks.ts` | 改过滤条件 | S3 |
| `frontend/.../subagent-event-handler.ts` | 不再被 SSE 调用 | S3 |
| `frontend/.../api/types.ts` | ContentEventData 移除 agent_id | S3 |

## 关键决策记录

- `parent_tool_call_id` 保留为元数据，仅记录来源关系，不参与任何路由或过滤
- 事件路由只有两层：Thread（SSE 连接）+ Turn（run_id）
- 子 Agent 实时流式输出（subagent buffer）删除，执行细节通过 Task Output REST API 按需拉取
- Blocking 子 Agent = 普通 tool_call → tool_result
- Async 子 Agent = 启动后属于 Thread，通过 task_start/task_done 通知

## 验证方案

1. 发送消息 → SSE 事件中无 `agent_id` 字段
2. Blocking 子 Agent → 普通 tool_call → tool_result，无 subagent buffer 分流
3. 后台 bash 命令 → `task_start` 事件有 `background: true`，无 `agent_id`，前端正确更新
4. 重启后端 → `agent_instances.json` 中的 agent_id 不变
5. 前端代码中搜索 `"main"` → 0 结果（与 agent_id 路由相关的）
6. 子 Agent 执行细节可通过 Task Output API 查看

## 不在本 Plan 范围

- member 跨 thread 共享 agent 实例 → 留给 Agent 协作调度
- agent_instances.json 的 GC（清理已删除 thread 的条目）→ 可复用 thread 删除逻辑
- 前端展示 agent 身份信息 → 另建 UI 需求
