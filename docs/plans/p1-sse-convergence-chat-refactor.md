# P1: SSE 收敛 + 持久连接 + Chat 渲染重构 + DetailBox Modal

## Context

Leon Chat Area 当前 SSE 事件 ~20 种，前缀区分来源（`subagent_task_*`、`background_task_*`），本质重复。SSE 采用 per-run 双通道模型（主通道临时 + activity 通道永久），Spec 要求合并为单一持久连接。前端 `flushSync` 每个 text chunk 强刷导致卡顿。ToolDetailBox 缺 Modal 展开态。历史加载无法按 `run_id` 分组重建 Turn。

P1 目标：SSE 协议收敛为 11 种事件 + 持久单通道 + 前端事件处理重写（含去 flushSync）+ DetailBox 加 Modal + run_id 写入消息 metadata。前后端同步改，不做兼容过渡。

## 前置：P0 一行修复（独立）

`frontend/app/src/hooks/use-sticky-scroll.ts` — 去 `characterData: true`。

---

## 新 SSE 协议契约

### 连接模型

**单一持久 SSE 连接**：`GET /api/threads/{thread_id}/events`

- 连接在进入 thread 时建立，离开时关闭
- 跨 run 保持，不因 run 结束而断开
- `run_start`/`run_done` 是流内事件标记，不是连接生命周期信号
- 支持 `?after=N` 断线续连（cursor-based）
- 替代当前的双通道（`/runs/events` + `/activity/events`）
- **Heartbeat**：每 30s 发送 SSE comment（`:ping`），防止代理层（Nginx/CloudFlare/ALB）idle timeout 断连

### 11 种事件 + P3 遗留

| 分类 | 事件 | payload 关键字段 |
|------|------|-----------------|
| 内容(5) | `text` | `{content, agent_id, parent_tool_call_id?, background?, message_id?, seq, run_id}` |
| | `tool_call` | `{id, name, args, agent_id, parent_tool_call_id?, background?, message_id?, seq, run_id}` |
| | `tool_result` | `{tool_call_id, name, content, metadata, agent_id, parent_tool_call_id?, background?, message_id?, seq, run_id}` |
| | `error` | `{error, agent_id, seq, run_id}` |
| | `cancelled` | `{message, cancelled_tool_call_ids, agent_id: "main", seq, run_id}` |
| 生命周期(3) | `task_start` | `{task_id, agent_id, parent_tool_call_id?, background?, type?: "bash"\|"agent", thread_id?, description?}` |
| | `task_done` | `{task_id, agent_id, parent_tool_call_id?, background?, status}` |
| | `task_error` | `{task_id, agent_id, parent_tool_call_id?, background?, error}` |
| 控制(3) | `status` | `{state, tokens, context, current_tool?, agent_id: "main"}` |
| | `run_start` | `{thread_id, run_id, agent_id, seq}` |
| | `run_done` | `{thread_id, run_id, agent_id, seq}` |

**P3 遗留**（P1 不动）：`command_progress`、`background_task_start/text/done/error`

### 路由规则

- 主 Agent：`agent_id = "main"`，无 `parent_tool_call_id`
- 子 Agent：`agent_id = task_id`，`parent_tool_call_id = parent_tool_call_id`，`background: true/false`
- 前端：先看 `type` 决定渲染方式，再看 `agent_id`/`parent_tool_call_id` 决定挂载位置

---

## 关键设计决策

| 问题 | 决策 | 理由 |
|------|------|------|
| SSE 连接模型 | **单一持久连接**，合并双通道 | Spec 要求。简化前端连接管理，`run_start`/`run_done` 为流内标记 |
| Subagent detail 事件进持久流？ | **不进**，仍路由到 subagent buffer | Spec 要求子 Agent 详情不嵌套在父 DetailBox，点"查看详情"通过 P3 的 `/tasks/{task_id}/stream` 独立拉取 |
| `done` 事件 | **删除**，用 `run_done` 替代 | `run_done` 是流内事件，不关连接。连接断开靠 SSE close 感知 |
| `background` 字段 | **添加到所有子 Agent/Task 事件** | Spec 要求区分前台子 Agent 和后台 Task |
| run_id 写入消息 metadata | **P1 实现** | Spec 要求历史加载按 run_id 分组重建 Turn |
| message-mapper.ts | **需要改**，按 run_id 分组 | 支持历史加载的 Turn 边界重建 |
| 临时 Turn ID 绑定 | P1 不动 | 正交，不影响协议变更 |

---

## 三条并行轨道

### 轨道 A：后端 SSE 收敛 + 持久连接

**A1. 合并为单一持久 SSE endpoint**
- 新 endpoint：`GET /api/threads/{thread_id}/events`
- 合并当前 `RunEventBuffer`（per-run）和 `activity_buffers`（per-thread）为统一的 per-thread 持久 buffer。注：`activity_buffers` 存在的唯一原因是 `RunEventBuffer` 随 run 结束而销毁，后台任务完成时 buffer 已不在，需要一个更长寿的通道接收"迟到"事件。持久 buffer 消除了这个限制，`activity_buffers` 不再需要
- buffer 生命周期：thread 创建时建立，thread 删除时销毁
- **内存管理**：ring buffer 模式，内存保留最近 ~2000 条事件，旧事件 fallback 到 SQLite `event_store`。`RunEventBuffer` 拆分为 `ThreadEventBuffer`（持久，跨 run）和 `RunEventBuffer`（仅 subagent 用，短生命周期）。`mark_done()` 和 `thread_event_buffers.pop()` 仅用于 subagent buffer，不用于 thread buffer
- run 事件写入同一个 buffer，`run_start`/`run_done` 作为分界标记
- 保留 `?after=N` + `Last-Event-ID` 断线续连
- `observe_run_events` 改为 `observe_thread_events`，从持久 buffer 读取
- endpoint 建立 SSE 前先校验 thread 存在性，不存在返回 HTTP 404（不是 SSE 事件）
- 关键文件：
  - `streaming_service.py` — 新增 `observe_thread_events`，修改 `start_agent_run` 写入持久 buffer
  - `services/event_buffer.py` — 持久 buffer 不随 run 结束而 `mark_done`
  - `routers/threads.py` — 新 endpoint，删除旧的 `/runs/events` 和 `/activity/events`

**A2. 主 Agent 事件加 `agent_id: "main"`**
- `streaming_service.py` — `emit()` 闭包统一注入 `agent_id: "main"`
- 影响：`text` `tool_call` `tool_result` `status` `error` `cancelled`

**A3. 去 `subagent_` 前缀 + 加 `background` 字段**
- `core/monitor/runtime.py` `emit_subagent_event` — 不再加前缀，改为注入 `agent_id`、`parent_tool_call_id`、`background`
- `core/task/subagent.py` Path A（`run_streaming`）— 直接发射的事件名统一：`task_text` → `text`，`task_tool_call` → `tool_call`，`task_tool_result` → `tool_result`，加 `agent_id`
- 内容事件保持原名（`text`/`tool_call`/`tool_result`）
- 生命周期事件保持 `task_start`/`task_done`/`task_error`

**A4. 路由条件改为 `agent_id` 检查**
- `streaming_service.py` activity drain 逻辑 — 从前缀检查改为 `agent_id` 检查
- `agent_id != "main"` 且内容事件 → subagent buffer only
- 生命周期事件 → 持久 buffer + subagent buffer

**A5. `done` → `run_done`**
- `streaming_service.py` 正常完成 / task agent 完成 — 改为 `run_done` 写入持久 buffer
- subagent buffer 关闭仍用 `run_done`（buffer 终止信号）
- `routers/threads.py` replay — `done` → `run_done`

**A6. run_id 写入消息 metadata**
- `streaming_service.py` `_run_agent_to_buffer` — 在处理 LangGraph 消息时，注入 `run_id` 到消息的 metadata
- 方案已验证（`examples/run_id_demo.py`）：`configurable` 传 `run_id` → node 读取 → 注入消息 metadata → checkpoint 持久化 → 历史加载 `metadata.run_id` 保留完好。全链路可行，含 checkpoint 持久化后的回读验证
- `run_id` 是核心键，每条消息必有，不存在无 `run_id` 的情况

### 轨道 B：前端事件处理重写

**B1. 类型定义更新**
- `api/types.ts` — 新 `STREAM_EVENT_TYPES`（11 + 5 P3 遗留）
- 添加 `ContentEventData`（含 `agent_id`/`parent_tool_call_id`/`background`）接口
- 删除 `SubagentTask*Data` 接口
- `run_done` 替代 `done`

**B2. 重写连接管理 — 单一持久 SSE**
- `hooks/use-thread-stream.ts` — 核心重写：
  - 单一 `EventSource` 连接到 `/api/threads/{thread_id}/events`
  - 进入 thread 时建立，离开时关闭
  - 删除当前的双通道逻辑（`streamEvents` + `streamActivityEvents`）
  - `run_start` 事件：设置 `isRunning=true`，开始新 Turn
  - `run_done` 事件：设置 `isRunning=false`，Turn 结束，**不关连接**
  - 断线续连用 `?after=N` + 指数退避（base 1s, max 30s, jitter ±20%，最多 10 次）。监听 `document.visibilitychange`，tab 可见时重置计数器并立即重连。区分可恢复错误（网络断开、5xx）和不可恢复错误（4xx），后者立即进入 `error` 状态不重连
  - `ConnectionPhase`：`idle | connecting | connected | reconnecting | error`。`error` = 重连 exhausted（10 次约 8.5 分钟），显示"重新连接"按钮
- `api/streaming.ts` — 删除 `streamActivityEvents`，`streamEvents` 改为 `streamThreadEvents`（持久）
- `api/sse-processor.ts` — 移除 `processChunk` 的 `terminal` 返回值（持久流无终止事件）。`run_done` 改为返回 `runEnded` 信号（通知上层 run 结束，但不关连接）

**B3. 重写事件分发**（核心）
- `hooks/stream-event-handlers.ts` — 新路由逻辑：
  ```
  status → setRuntimeStatus
  agent_id != "main" → handleSubagentEvent
  agent_id == "main" → EVENT_HANDLERS[type]
  command_*/background_task_* → onActivityEvent (P3 遗留)
  ```
- **去 `flushSync`**：`handleText` 改普通 setState
- **去 segments 重建**：`handleText` 不整体重建 segments 数组，改为追加/更新最后一个 segment（Spec 第八章性能 #2）
- 去 200ms setTimeout（或加 cleanup）

**B4. 重写子 Agent handler**
- `hooks/subagent-event-handler.ts` — MUTATORS key 从 `subagent_task_text` 改为 `text`

**B5. 去 `use-stream-handler.ts` 中的 `flushSync`**
- reconnect 路径的 `flushSync` → 普通 setState
- `handleSendMessage` 中的 `flushSync` **保留**（冷路径，optimistic UI 需要）

**B6. message-mapper.ts — 按 run_id 分组**
- 历史加载时，从消息 `metadata.run_id` 重建 Turn 边界
- 映射规则：
  - 相同 `run_id` 的连续消息 = 一个 Turn
  - 相同 `run_id` 内的 `source: "system"` HumanMessage = fold 进 Turn 作为 notice segment（Agent running 时收到的 Notification）
  - 不同 `run_id` 之间的 `source: "system"` HumanMessage = Turn 间 Notification 分割线（Agent idle 时到达，触发了新 Turn）
  - 不同 `run_id` 的 AIMessage = 新 Turn 开始
- `run_id` 是核心键，每条消息必有，无需回退兼容逻辑

### 轨道 C：前端渲染重构

**C1. DetailBox Modal**（新文件）
- `components/chat-area/DetailBoxModal.tsx` — shadcn/ui `Dialog`
- 内容：按时间序展示 Turn 完整执行细节
  - 中间 AI text（被 tool call 打断的）
  - ToolCall + ToolResult（两行紧凑格式，spec 第四章样式）
  - Notice segments（Agent running 时收到的 Notification）
  - Subagent steps + "查看详情"链接（interim：切到 Agents tab + focus 对应 step，P3 Task Output Stream API 就绪后改为 `/tasks/{task_id}/stream` 实时流式详情页）

**C2. ToolDetailBox 改造**
- `components/chat-area/ToolDetailBox.tsx`
- onClick 从 `onFocusStep` 改为打开 Modal（C1）
- 保持 `onFocusStep` prop 但不再使用（P2 删除）
- 三态高度：Silent(80px) / Executing(130px) / Expanded(Modal)

**C3. AssistantBlock 微调**
- 中间 text segments 已被隐藏（只显示最后一个），确保它们在 Modal 中可访问
- 无大改动，当前逻辑已对齐 spec

---

## 轨道间依赖

```
A1 (持久连接) ──→ B2 (前端连接重写) ──→ B3 (事件分发)
A2-A5 (事件格式) ←── 协议契约 ──→ B1 (类型定义)
A6 (run_id metadata) ──→ B6 (mapper 分组)
C1-C3 (渲染) ── 完全独立
```

**硬依赖**：
- B2 依赖 A1：前端持久连接需要后端新 endpoint
- B6 依赖 A6：mapper 分组需要后端写入 run_id

**可并行**：
- A2-A5 和 B1+B3+B4 按协议契约各自开发
- C1-C3 与 A/B 完全并行

---

### 建议：P1a / P1b 拆分

P1 涉及 17+ 文件的原子改动，建议拆为两个可独立验证的阶段：

- **P1a（后端）**：A1-A6，可用 curl 验证（持久连接、事件格式、heartbeat、run_id）
- **P1b（前端）**：B1-B6 + C1-C3，依赖 P1a 的后端 endpoint

P1a 完成后有一个稳定的中间检查点，降低全量联调的风险。

## 实施顺序

| 步骤 | 内容 | 并行关系 |
|------|------|---------|
| 0 | P0: use-sticky-scroll 去 characterData | 独立 |
| 1 | B1: types.ts 新类型定义（定合同） | 先行 |
| 2a | A1: 后端持久 buffer + 新 endpoint | 并行 ↓ |
| 2b | A2-A5: 事件格式收敛 | 并行 ↓ |
| 2c | A6: run_id 写入消息 metadata | 并行 ↓ |
| 2d | B2: 前端持久连接重写 | 并行 ↑（可先 mock） |
| 2e | B3-B5: 前端事件分发重写 | 并行 ↑ |
| 2f | C1-C3: DetailBox Modal + 渲染 | 并行 ↑ |
| 3 | B6: message-mapper 按 run_id 分组 | 依赖 A6 |
| 4 | 联调：前后端对接验证 | 全部完成后 |

## 验证方案

1. **持久连接**：curl 订阅 `/events`，发消息触发 run，确认 `run_start` → 内容事件 → `run_done`，连接不断开
2. **多 run**：同一连接内触发第二次 run（通过 Notification），确认两个 run 的事件都在同一流中
3. **断线续连**：断开后用 `?after=N` 重连，确认不丢事件
4. **事件格式**：确认所有事件带 `agent_id`，子 Agent 事件带 `parent_tool_call_id` + `background`
5. **子 Agent**：触发 task agent → `task_start` → 父 Turn DetailBox 更新 → `task_done`
6. **Modal**：点击 DetailBox → Modal 弹出 → 完整时间线（中间 text + tools + notices）
7. **历史回放**：刷新页面 → message-mapper 按 `run_id` 分组 → Turn 边界与流式一致
8. **取消**：mid-run 取消 → `cancelled` 事件正常，连接保持
9. **性能**：流式输出不卡顿（无 flushSync，无 segments 重建）
10. **P3 兼容**：后台命令仍通过 `command_progress` 更新

## 关键文件清单

### 后端
| 文件 | 改动 |
|------|------|
| `backend/web/services/streaming_service.py` | 持久 buffer、事件格式、路由、run_done |
| `backend/web/services/event_buffer.py` | 持久 buffer 生命周期 |
| `backend/web/routers/threads.py` | 新 `/events` endpoint，删旧双 endpoint |
| `core/monitor/runtime.py` | 去 subagent_ 前缀，加 agent_id/parent_tool_call_id/background |
| `core/task/subagent.py` | Path A (run_streaming) 事件名统一 + agent_id |
| `backend/web/services/event_store.py` | 适配持久 buffer 的事件持久化 |

### 前端
| 文件 | 改动 |
|------|------|
| `api/types.ts` | 新事件类型 + ContentEventData 接口 |
| `api/streaming.ts` | 单 endpoint，删双通道 |
| `api/sse-processor.ts` | 去 done 终止，适配持久流 |
| `hooks/use-thread-stream.ts` | 核心重写：单连接，run_start/run_done 为流内标记 |
| `hooks/use-stream-handler.ts` | 去 flushSync，适配新连接模型 |
| `hooks/stream-event-handlers.ts` | agent_id 路由，去 flushSync |
| `hooks/subagent-event-handler.ts` | 新事件名，parent_tool_call_id |
| `api/message-mapper.ts` | 按 run_id 分组重建 Turn |
| `components/chat-area/DetailBoxModal.tsx` | 新文件：Modal 组件 |
| `components/chat-area/ToolDetailBox.tsx` | onClick → Modal，三态 |
| `components/chat-area/AssistantBlock.tsx` | 确保中间 text 可传给 Modal |

## 不在 P1 范围

- Steps tab 删除、onFocusStep 链路清理 → P2
- Background Task 统一（CommandNotification、持久化、REST API）→ P3
- ToolCall 富渲染（代码编辑器、Diff 视图）→ P4
- 虚拟滚动 → 未来
