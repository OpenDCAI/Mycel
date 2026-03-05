# P3: Background Task 统一 + Task Output API

## Context

P1 定义了 11 种 SSE 事件，其中 `task_start`/`task_done`/`task_error` 已预留给 Background Task，但 P1 只用它们处理前台子 Agent 生命周期。后台任务仍走旧的 `command_progress` + `background_task_*` 通道（P1 标记为"P3 遗留"）。P2 删除了 `useActivities` hook 和 Activities UI，将 `onActivityEvent` 改为 no-op。

P3 完成 Spec 第六章的 Background Task 统一：合并两套后台机制为一套，建立 Task Output REST API，后端改为发射统一事件，前端建立数据层。

**前置依赖**：P1（持久 SSE + 11 种事件类型已定义）。软依赖 P2（旧 Activities 系统已清除——仅前端 S4-S6 依赖，后端 S1-S3 可与 P2 并行）

---

## 关键发现

### 当前两套后台机制

| | Background Bash | Background Task Agent |
|---|---|---|
| 触发 | `run_command(Blocking=false)` | `create_task(RunInBackground=true)` |
| 执行 | `asyncio.create_subprocess_shell` | `asyncio.create_task(_execute_agent())` |
| 状态存储 | `_RUNNING_COMMANDS` 模块级 dict（`executor.py`） | `_active_tasks` + `_task_results` 实例 dict（`SubagentRunner`） |
| SSE 事件 | `command_progress`（轮询 2s 发一次，含 output_preview） | `background_task_start/text/done/error` |
| 前端消费 | `useActivities` → `ActivitySection` | `useActivities` → `ActivitySection` |
| 取消 | `process.terminate()` | `asyncio.Task.cancel()` |
| LLM 查询 | `command_status` 工具 | `TaskOutput` 工具 |

两套机制共享相同的生命周期模型（start → running → done/error/cancelled），但状态分散在不同位置，事件格式不同，取消路径不同。

### 统一后的目标模型（Spec 第六章）

- SSE 只发轻量通知：`task_start` / `task_done` / `task_error`（已在 P1 协议中定义）
- 不再通过 SSE 推送 output 内容（去掉 `command_progress.output_preview` 和 `background_task_text`）
- 前端通过 REST API 拉取完整状态和输出
- `task_done` 触发前端 re-fetch
- Background Task 完成后注入 Notification 到主 Agent 消息队列（唤醒 idle Agent 或归入当前 Turn）

### CommandNotification 缺失（Analysis 标记的前置依赖）

Task Agent 完成后已有 `_inject_task_notification()` 将结果注入消息队列。Background Bash **完全没有**对应机制——命令完成后只发 SSE 事件，Agent 无法自动感知，只能主动调 `command_status` 轮询。

P3 必须补上：Background Bash 完成后，也通过消息队列注入 CommandNotification，让 idle Agent 自动醒来处理结果。

### 持久化决策

Analysis 标记"Task 结果持久化"为前置依赖。P3 范围内的决策：

- **P3 用内存 registry**：`BackgroundTaskRegistry` 挂在 `LeonAgent` 实例上，进程生命周期内有效
- **后果**：进程重启后 Task Output API 返回空，历史 Background Task 信息丢失
- **可接受原因**：Background Task 本身是运行时概念（进程在跑才有后台任务），重启后旧任务的进程/协程也已丢失，数据与状态一致
- **未来扩展**：如需跨重启查询历史任务（如审计），可在 registry 层加 SQLite 写入，API 层不变

### LLM 工具不动

`command_status` 和 `TaskOutput` 是 LLM 用的工具（Agent 自己轮询后台任务状态），不是前端 API。它们的内部实现可以改为从统一 registry 读取，但工具接口不变。

### Cancel 端点已存在

`POST /api/threads/{thread_id}/tasks/{task_id}/cancel` 和 `POST /api/threads/{thread_id}/commands/{command_id}/cancel` 已存在。统一后合并为一个 cancel 端点，通过 registry 路由到对应的取消逻辑。

---

## 实施步骤

### S1. 后端：BackgroundTaskRegistry

**新建 `core/task/registry.py`**

统一的后台任务注册中心，替代分散的状态存储：

```python
class TaskEntry(BaseModel):
    task_id: str
    type: Literal["bash", "agent"]
    description: str              # 命令行 or 任务描述（与 P1 task_start payload 对齐）
    status: Literal["running", "done", "error", "cancelled"]
    started_at: float
    finished_at: float | None = None
    parent_tool_call_id: str | None = None
    # 输出（懒加载，不在列表 API 返回）
    output: str | None = None
    exit_code: int | None = None  # bash only
    error: str | None = None

class BackgroundTaskRegistry:
    """Per-agent-instance registry. 挂在 LeonAgent 上，随 agent 生命周期。"""

    def register(self, entry: TaskEntry) -> None: ...
    def update_status(self, task_id: str, status: str, **kwargs) -> None: ...
    def get(self, task_id: str) -> TaskEntry | None: ...
    def list_tasks(self) -> list[TaskEntry]: ...
    def cancel(self, task_id: str) -> bool: ...
```

**生命周期**：挂在 `LeonAgent` 实例上（或通过 `RuntimeMonitor` 访问），不是模块级全局变量。

**改动**：
- `core/command/middleware.py` — `_execute_async()` 中注册 bash task 到 registry
- `core/command/bash/executor.py` — `_RUNNING_COMMANDS` 保留（进程管理），但不再是状态查询的唯一来源
- `core/task/subagent.py` — `run()` 中注册 agent task 到 registry
- `core/task/middleware.py` — `TaskOutput` 工具从 registry 读取（回退到 `_task_results`）
- `core/command/middleware.py` — `command_status` 工具从 registry 读取（回退到 executor）

### S2. 后端：SSE 事件统一 + CommandNotification 注入

**`core/command/middleware.py`**
- `_monitor_async_command()` — 停止每 2s 发 `command_progress`
- 改为：启动时通过 `runtime.emit_activity_event` 发 `task_start`（一次），完成时发 `task_done` 或 `task_error`（一次）
- **顺序约束**：`registry.register(entry)` 必须在 `emit("task_start")` 之前完成，确保前端 re-fetch 时 task 已在 registry 中
- `task_start` payload：`{task_id, agent_id, parent_tool_call_id?, background: true, type: "bash", description: command_line}`
- `task_done` payload：`{task_id, agent_id, parent_tool_call_id?, background: true, status: "done"}`
- **顺序约束**：`registry.update_status(task_id, "done", output=...)` 必须在 `emit("task_done")` 之前完成，确保前端 re-fetch 时 output 已就绪
- 同时更新 registry 状态
- **新增 CommandNotification 注入**：命令完成后，参照 `_inject_task_notification()` 逻辑，将命令结果（exit_code + output 摘要）封装为 CommandNotification XML，通过 `queue_manager.enqueue()` 注入主 Agent 消息队列。idle Agent 自动醒来处理结果，running Agent 将其归入当前 Turn

**`core/task/subagent.py`**
- `_execute_agent_streaming()` — 停止发 `background_task_start/text/done/error`
- 改为：发 `task_start`（已有，保持）、`task_done`/`task_error`（已有，保持格式）
- 关键变化：去掉 `background_task_text`（不再流式推送 output）
- `subagent_task_*` 系列事件不受影响（那是前台子 Agent 的 AgentsView 渲染通道，P1 已处理）

**`backend/web/services/streaming_service.py`**
- `activity_queue` drain 逻辑 — 去掉 `command_progress` 和 `background_task_*` 的特殊处理
- `task_start`/`task_done`/`task_error` 已经走 P1 的统一路由（生命周期事件 → 持久 buffer）

**结果**：5 种旧事件（`command_progress`、`background_task_start/text/done/error`）→ 3 种已有事件（`task_start`、`task_done`、`task_error`）

### S3. 后端：Task Output REST API

**`backend/web/routers/threads.py`** — 新增三个 endpoint：

```
GET /api/threads/{thread_id}/tasks
→ [
    { task_id, type: "bash",  description: "npm test",  status: "running", started_at },
    { task_id, type: "agent", description: "代码审查",   status: "done",    started_at, finished_at },
  ]

GET /api/threads/{thread_id}/tasks/{task_id}
→ { task_id, type, description, status, output, exit_code?, error? }

GET /api/threads/{thread_id}/tasks/{task_id}/stream
→ SSE 流，实时推送任务输出（bash 和 agent 统一接口）
```

**Task Output Stream**（`/stream`）：
- **bash**：tail subprocess stdout，实时推 output chunks（替代旧 `command_progress` 的 2s 轮询）
- **agent**：从 subagent buffer 读取，实时推 `text`/`tool_call`/`tool_result` 事件（替代 P1 的独立 subagent buffer 拉取机制）
- 任务完成时发 `task_done` 事件并关闭流
- 任务已完成时直接返回完整 output + `task_done` 并关闭
- 前端按需建连（用户打开详情时才连），不看不连

**实现**：从 `BackgroundTaskRegistry`（挂在当前 agent 实例上）读取。通过 `app.state` 中缓存的 agent 引用访问 registry。stream endpoint 通过 registry 的 `type` 字段决定数据源（subprocess stdout vs subagent buffer）。

**Cancel 端点合并**：
- 现有 `/commands/{command_id}/cancel` 和 `/tasks/{task_id}/cancel` 合并为：
- `POST /api/threads/{thread_id}/tasks/{task_id}/cancel`
- 内部通过 registry 的 `type` 字段决定是 `process.terminate()` 还是 `asyncio.Task.cancel()`
- **幂等性**：对已 completed/cancelled 的 task 再次 cancel 返回 200（不是 404/409），body 标注 `{"cancelled": false, "reason": "already_completed"}`

### S4. 前端：类型 + 事件处理

**`api/types.ts`**
- 从 `STREAM_EVENT_TYPES` 移除 5 种旧事件：`command_progress`、`background_task_start`、`background_task_text`、`background_task_done`、`background_task_error`
- `task_start`/`task_done`/`task_error` 已在 P1 定义，无需新增
- 新增 `BackgroundTask` 类型（对应 REST API 响应）
- 删除 `Activity` 类型（P2 遗留的导出，如果还在）

**`hooks/stream-event-handlers.ts`**
- 移除 `command_*` / `background_task_*` 的 `startsWith` 路由分支
- `task_start`/`task_done`/`task_error` 中 `background: true` 的事件 → 转发到 `onBackgroundTaskEvent` 回调
- `background: false`（或无 background 字段）→ 保持现有逻辑（前台子 Agent 生命周期）

**`api/sse-processor.ts`**（如有残留的旧事件类型校验）
- 同步更新允许的事件类型列表

### S5. 前端：Background Task 数据层

**新建 `hooks/use-background-tasks.ts`**

```typescript
interface BackgroundTask {
  task_id: string;
  type: "bash" | "agent";
  description: string;
  status: "running" | "done" | "error" | "cancelled";
  started_at: number;
  finished_at?: number;
}

interface UseBackgroundTasksReturn {
  tasks: BackgroundTask[];
  fetchTasks: () => Promise<void>;
  fetchTaskOutput: (taskId: string) => Promise<TaskOutput>;
  streamTaskOutput: (taskId: string) => EventSource;  // 实时流式输出
  cancelTask: (taskId: string) => Promise<void>;
  handleBackgroundTaskEvent: (event: StreamEvent) => void;
}
```

- `handleBackgroundTaskEvent`：SSE 通知处理器
  - `task_start` → 追加到 tasks 列表（optimistic，不等 API）
  - `task_done` / `task_error` → 更新本地状态 + 触发 re-fetch（拿最新 output）
- `fetchTasks`：`GET /api/threads/{thread_id}/tasks` → 全量刷新
- `fetchTaskOutput`：`GET /api/threads/{thread_id}/tasks/{task_id}`（完成后的完整输出）
- `streamTaskOutput`：`GET /api/threads/{thread_id}/tasks/{task_id}/stream`（执行中的实时流，用户打开详情时建连，关闭时断开）
- `cancelTask`：`POST /api/threads/{thread_id}/tasks/{task_id}/cancel` + optimistic 更新

**`pages/ChatPage.tsx`**
- 引入 `useBackgroundTasks()`
- 将 `handleBackgroundTaskEvent` 传入 stream handler（替代 P2 的 no-op `onActivityEvent`）

### S6. 前端：接口清理

**`hooks/use-stream-handler.ts`**
- `onActivityEvent` 参数重命名为 `onBackgroundTaskEvent`（语义更准确）
- 或直接删除该间接层，让 stream-event-handlers 直接调用

**`backend/web/routers/threads.py`**
- 删除旧的 cancel 端点（`/commands/{command_id}/cancel`），统一走 `/tasks/{task_id}/cancel`

---

## 轨道间依赖

```
S1 (Registry) ──→ S2 (SSE 统一) ── 必须先有 registry 才能发 task_id
              ──→ S3 (REST API) ── API 从 registry 读取
S2 (SSE 统一) ──→ S4 (前端事件) ── 前端需要对齐新事件格式
S3 (REST API) ──→ S5 (数据层)   ── hook 调 API
S4 + S5       ──→ S6 (清理)     ── 最后清理
```

**可并行**：
- S1 + S4 前端类型更新（按协议契约各自开发）
- S2 + S3 可并行（都依赖 S1，但彼此独立）
- S5 可在 S3 完成后开始（需要 API endpoint）

---

## 关键文件清单

### 后端

| 文件 | 改动 | 步骤 |
|------|------|------|
| `core/task/registry.py` | **新建**：BackgroundTaskRegistry | S1 |
| `core/command/middleware.py` | 注册 bash task，停发 `command_progress`，改发 `task_start`/`task_done` | S1+S2 |
| `core/command/bash/executor.py` | 保留进程管理，registry 补充状态查询 | S1 |
| `core/task/subagent.py` | 注册 agent task，去 `background_task_text`，保持 `task_start`/`task_done` | S1+S2 |
| `core/task/middleware.py` | `TaskOutput` 工具从 registry 读取 | S1 |
| `core/monitor/runtime.py` | `emit_activity_event` 逻辑可能微调（如果路由变化） | S2 |
| `backend/web/services/streaming_service.py` | drain 逻辑去旧事件类型 | S2 |
| `backend/web/routers/threads.py` | 新增 tasks list/output API，合并 cancel 端点 | S3+S6 |

### 前端

| 文件 | 改动 | 步骤 |
|------|------|------|
| `api/types.ts` | 移除 5 种旧事件类型，新增 `BackgroundTask` 类型 | S4 |
| `hooks/stream-event-handlers.ts` | 移除 `command_*`/`background_task_*` 分支，background 路由 | S4 |
| `hooks/use-background-tasks.ts` | **新建**：数据层 hook | S5 |
| `pages/ChatPage.tsx` | 引入 `useBackgroundTasks`，替代 no-op | S5 |
| `hooks/use-stream-handler.ts` | `onActivityEvent` → `onBackgroundTaskEvent` | S6 |
| `api/sse-processor.ts` | 同步事件类型列表（如有） | S4 |

### 新建/删除的文件

| 文件 | 操作 |
|------|------|
| `core/task/registry.py` | **新建**：BackgroundTaskRegistry |
| `hooks/use-background-tasks.ts` | **新建**：前端数据层 hook |

### 不动的文件

| 文件 | 原因 |
|------|------|
| `core/command/bash/executor.py` 的进程管理 | `_RUNNING_COMMANDS` 仍负责进程生命周期，registry 补充状态查询 |
| `hooks/subagent-event-handler.ts` | 处理前台子 Agent（`subagent_task_*`），与 Background Task 无关 |
| `components/tool-renderers/` | 不涉及 |

---

## 不在 P3 范围

- **Background Task UI 设计**（展示位置、面板样式）→ 后续 UX 决策（Spec 明确延期）
- **取消按钮 UI** → 后续 UX 决策
- **ToolCall 富渲染** → P4
- **虚拟滚动** → 未来

P3 只建管道（registry + REST API + SSE 统一 + 前端数据层），不建 UI。数据层就绪后，后续可在任何 UI 位置消费 `useBackgroundTasks()` 的数据。

---

## 验证方案

1. **Bash 后台命令**：`run_command("sleep 10 && echo done", Blocking=false)` → SSE 收到 `task_start`（一次）→ 10s 后收到 `task_done`（一次）→ 无 `command_progress` 事件
2. **Bash CommandNotification**：后台命令完成后，idle Agent 自动醒来处理结果（CommandNotification 注入消息队列触发新 Turn）
3. **Task Agent 后台**：`create_task("...", RunInBackground=true)` → SSE 收到 `task_start` → 完成后 `task_done` → 无 `background_task_text` 流
4. **Task List API**：`GET /api/threads/{thread_id}/tasks` → 返回当前所有后台任务列表
5. **Task Output API**：`GET /api/threads/{thread_id}/tasks/{task_id}` → 返回完整输出
6. **Task Output Stream**：`GET /api/threads/{thread_id}/tasks/{task_id}/stream` → bash 命令实时输出流；agent 任务实时 text/tool_call 流；任务完成时流自动关闭
7. **Cancel**：`POST /api/threads/{thread_id}/tasks/{task_id}/cancel` → bash 进程被 terminate / agent task 被 cancel
8. **前端数据层**：`task_done` SSE 事件触发 `useBackgroundTasks` 自动 re-fetch
9. **LLM 工具不受影响**：`command_status` 和 `TaskOutput` 工具正常工作
10. **无旧事件**：SSE 流中不再出现 `command_progress`、`background_task_start/text/done/error`
11. **前端无 console 报错**：旧事件类型不再到达，新事件正确路由
