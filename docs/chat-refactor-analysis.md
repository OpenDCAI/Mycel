# Chat Area Refactor — 可执行性分析

基于 [chat-refactor-spec.md](./chat-refactor-spec.md)，对照当前代码的落地分析。

## 一、Spec 与现状匹配度

### 已对齐（不需要改或改动小）

| Spec 要求 | 现状 | 位置 |
|---|---|---|
| 主消息区只显示最近的 AI text | 已实现：`textSegs[textSegs.length - 1]` | `AssistantBlock.tsx:62` |
| run_id 注入每条事件 | 已实现：每个事件 data 自动注入 `_run_id` | `streaming_service.py:245` |
| Notice 分割 Turn 内容 | 已实现：`splitPhases()` 按 NoticeSegment 分割 | `AssistantBlock.tsx` |
| 主 Turn 取消 | 已实现：`POST /threads/{id}/runs/cancel` | `streaming_service.py` |

### 有基础需重构

| Spec 要求 | 现状 | 差距 |
|---|---|---|
| DetailBox 三态（静默/执行/展开） | ToolDetailBox 只有两种高度（80px/130px），无 Modal | 加 Modal + 状态机 |
| ToolCall 富渲染 | `getStepSummary()` 有摘要逻辑，无代码编辑器/Diff | 按工具类型分别实现 |
| Turn 按 run_id 分组 | 一个 Turn = 一次 SSE 连接，不是按 run_id | 改分组逻辑 |
| SSE 事件收敛 | 发射集中在 `streaming_service.py` + `subagent.py`，路由逻辑清晰 | 可重构，不需推翻 |

### 完全缺失

| Spec 要求 | 现状 | 说明 |
|---|---|---|
| Task Output REST API | 不存在 | 无 `GET /tasks`，无 `GET /tasks/:id/output` |
| Task 结果持久化 | `_task_results` 内存 dict，进程重启即丢 | 需 SQLite 表 |
| CommandNotification | **不存在** | 后台命令完成只发 `command_progress` SSE，不注入消息队列 |
| Background Bash 统一为 Task | 命令和 Task Agent 完全独立的两套系统 | 需统一数据模型 |

## 二、关键发现

### SSE 事件实际数量

代码中实际 ~20 种（非 Spec 原文的 26 种），分布如下：

**主 Agent 流（8 种）**：`text` `tool_call` `tool_result` `status` `done` `cancelled` `error` `new_run`

**Activity 通道（6 种）**：`run_done` `command_progress` `background_task_start` `background_task_text` `background_task_done` `background_task_error`

**Subagent 前缀（6 种）**：`subagent_task_start` `subagent_task_text` `subagent_task_tool_call` `subagent_task_tool_result` `subagent_task_done` `subagent_task_error`

路由逻辑在 `streaming_service.py:476-532`：subagent 内容事件（text/tool_call/tool_result）被静默丢弃不发给父 SSE，仅路由到 subagent 自己的 `RunEventBuffer`。

### run_id 机制

- `run_id = str(uuid4())`，在 `start_agent_run()` 生成
- 已注入每条 SSE 事件的 data payload（`_run_id` 字段）
- **不在 LangGraph 消息 metadata 里**——需要额外写入才能支持历史加载的 Turn 分组
- 持久化在 `run_events` SQLite 表（`thread_id, run_id, seq`）

### status 事件内容

```json
{
  "state": { "state": "active|idle", "flags": {...}, "error": {...} },
  "tokens": { /* TokenMonitor metrics */ },
  "context": { /* ContextMonitor metrics */ },
  "current_tool": "tool_name"  // 仅 ToolMessage 后有
}
```

每个 ToolMessage 后发一次（带 `current_tool`），run 结束时发一次（不带）。

### done 事件用途

`done` 信号 SSE 消费端"流结束了，关连接"。4 个发射点：
1. 主 run 正常完成（`streaming_service.py:558`）
2. Subagent buffer 关闭时注入（`:525`）
3. Replay 回放结束时注入（`threads.py:383,400`）
4. Task agent run 结束（`:789`）

Spec 要求删除 `done`，改为 SSE 连接持久化。需要改前端 `EventSource` 的重连逻辑。

### CommandNotification 缺失

Spec Section 一列了三种 Notification，但 CommandNotification **完全未实现**：
- 后台命令完成后只发 `command_progress` SSE 事件（`done: true`）
- 不注入消息队列，Agent 无法自动感知
- Agent 只能通过主动调 `command_status` 工具查结果

要统一为 Background Task，必须先补上注入机制。

### AgentsView 依赖 StepsView

`AgentsView.tsx:140-146` 内部复用了 `StepsView` 渲染子 Agent 的工具流。删除 Steps tab 时不能直接删 `StepsView.tsx`，需要：
- 将 StepsView 中 AgentsView 需要的渲染逻辑提取出来，或
- 让 AgentsView 内联自己的渲染

### onFocusStep 链路

删除 Steps tab 需要清理整条链路（4 个文件）：

```
ChatPage (handleFocusStep → 切换到 steps tab)
  → ChatArea → AssistantBlock → ToolDetailBox (onClick)
  → ComputerPanel → StepsView (scroll/highlight)
```

ToolDetailBox 的点击行为需要改为打开 Modal（对应 Spec 的 DetailBox 展开态）。

## 三、风险矩阵

| 模块 | 工作量 | 风险 | 原因 |
|---|---|---|---|
| 性能修复（flushSync / MutationObserver） | 小 | 低 | 改动点明确，可独立做 |
| Steps tab 删除 + Activity 清理 | 小 | 中 | AgentsView 依赖 StepsView，需先处理 |
| DetailBox Modal + 富渲染 | 中 | 低 | 纯前端，不涉及协议 |
| SSE 事件收敛（前后端同步改） | 中 | 中 | 原子操作，改动期间系统不可用 |
| Background Task 统一 + API | 大 | 高 | 三个前置缺失（CommandNotification / 持久化 / API） |

## 四、依赖关系

```
性能修复 ──────────────────────────── 独立，随时可做

Steps tab 删除 ← AgentsView 依赖 StepsView（需先处理）

SSE 收敛 ←→ 前端 Chat 渲染重构（必须原子操作）
  │
  └── DetailBox Modal + 富渲染（可同步或之后做）

Background Task 统一 ← CommandNotification（必须先补）
  │                  ← Task 持久化（必须先做）
  └── Task Output API（依赖持久化）
```

## 五、分阶段建议

| 阶段 | 内容 | 前置 | 预期效果 |
|---|---|---|---|
| **P0** | 性能修复：去 flushSync、MutationObserver characterData | 无 | 流式输出卡顿消除 |
| **P1** | SSE 收敛 + Chat 渲染重构 + DetailBox Modal | 无（与 P0 并行） | 20→11 事件类型，主消息区干净 |
| **P2** | Steps tab 删除 + onFocusStep 链路清理 | P1 | ComputerPanel 精简，DetailBox Modal 替代 |
| **P3** | Background Task 统一（补 CommandNotification → 持久化 → REST API） | P1 | 后台任务统一管理，结果不丢失 |
| **P4** | ToolCall 富渲染（代码编辑器、Diff 视图） | P1 | 工具结果可视化体验提升 |

P0 + P1 是核心，改完就能看到明显的体验和性能提升。P3 最重但可推后——当前功能不会因没有 Task Output API 而坏掉。

## 六、受影响文件清单

### 前端需改动

| 文件 | 改动类型 | 阶段 |
|---|---|---|
| `api/types.ts` | 重写事件类型、ChatEntry 类型 | P1 |
| `hooks/stream-event-handlers.ts` | 重写事件分发（去 flushSync + 新事件类型） | P0+P1 |
| `hooks/subagent-event-handler.ts` | 合并到主 handler | P1 |
| `hooks/use-stream-handler.ts` | 去 flushSync + 去 onActivityEvent | P0+P1 |
| `hooks/use-sticky-scroll.ts` | 去 characterData | P0 |
| `hooks/use-activities.ts` | 删除 | P2 |
| `hooks/use-app-actions.ts` | 去 focusedStepId | P2 |
| `components/chat-area/ToolDetailBox.tsx` | 重构为 DetailBox + Modal | P1 |
| `components/chat-area/AssistantBlock.tsx` | 适配新 Turn 分层结构 | P1 |
| `components/chat-area/ChatArea.tsx` | 去 onFocusStep | P2 |
| `components/computer-panel/index.tsx` | 删 steps tab + activities | P2 |
| `components/computer-panel/StepsView.tsx` | 提取 AgentsView 所需部分，其余删除 | P2 |
| `components/computer-panel/TabBar.tsx` | 删 steps tab entry | P2 |
| `components/computer-panel/types.ts` | 删 steps + activity props | P2 |
| `pages/ChatPage.tsx` | 去 useActivities + activity props | P2 |

### 后端需改动

| 文件 | 改动类型 | 阶段 |
|---|---|---|
| `backend/web/services/streaming_service.py` | 事件类型重命名 + 路由重构 + 去 done | P1 |
| `core/task/subagent.py` | 事件统一（去 subagent_ 前缀 + 加 agent_id） | P1 |
| `core/monitor/runtime.py` | 去 `emit_subagent_event` 前缀逻辑 | P1 |
| `core/command/middleware.py` | 补 CommandNotification 注入 + 去 command_progress | P3 |
| `core/task/types.py` | Background Task 统一数据模型 | P3 |
| `backend/web/main.py` (routes) | 新增 Task Output API endpoints | P3 |
| 新文件：task 持久化层 | SQLite 表 + repo | P3 |
