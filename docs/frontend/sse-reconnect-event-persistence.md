# SSE 重连 + 持久化事件日志：消除前端数据源竞争

## Context

前端有两个数据源竞争同一个 `entries` 状态：
- `loadThread` → `mapBackendEntries` → `setEntries(全量覆盖)`，ID 格式 `hist-turn-3`
- SSE 增量流 → `processStreamEvent` → 用前端临时 `turnId` 匹配追加，ID 格式 `turn-xxx-abc`

切换 thread 或刷新页面时，快照覆盖 SSE 写入的 turn（ID 不同），导致内容丢失、每刷新一次"动一点"。

**根本解决**：两个数据源共享同一套 ID（LangGraph message UUID）+ 事件持久化到 SQLite。

## 关键发现

- LangGraph 自动给每条消息分配稳定 UUID（`msg.id`），checkpoint 持久化，streaming 时就有
- `tool_calls[].id` = LLM 生成的稳定 ID（`call_xxx`）
- 现有 SQLite DB（`~/.leon/leon.db`）已有 checkpoints/writes/thread_config 等表

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Turn 粒度 | 一个 Run = 一个 Turn | 产品体验，用户看到一条完整消息 |
| Turn ID | 第一条 AIMessage 的 UUID | 快照和 SSE 共享同一 ID，无需额外映射 |
| 事件持久化 | SQLite `run_events` 表 | 服务端重启后可回放，复用现有 DB |
| Text 去重 | 不需要 | 时序保证：`await loadThread` 完成后才启动 `observeRun` |
| Tool 去重 | `tool_call_id` 精确匹配 | segments 里已有该 ID → skip |
| 竞态消除 | 时序控制，非对账 | 重连 effect 串行：`await loadThread` → `observeRun` |

---

## Step 1: 后端 — `serialize_message` 带 `msg.id`

**文件**: `backend/web/utils/serializers.py`（+1 行）

```python
def serialize_message(msg):
    return {
        "id": getattr(msg, "id", None),          # 新增：LangGraph UUID
        "type": msg.__class__.__name__,
        "content": getattr(msg, "content", ""),
        "tool_calls": getattr(msg, "tool_calls", []),
        "tool_call_id": getattr(msg, "tool_call_id", None),
    }
```

## Step 2: 后端 — SSE 事件带 `message_id`

**文件**: `backend/web/services/streaming_service.py`（+3 行，改 3 处 `buf.put`）

每类事件的 `data` JSON 中加 `message_id` 字段：

- `text` 事件：`"message_id": msg_chunk.id`（line ~202）
- `tool_call` 事件：`"message_id": msg.id`（line ~234）
- `tool_result` 事件：`"message_id": msg.id`（line ~251）

同时引入 `emit()` 辅助函数，在 `buf.put()` 之前同步写入 SQLite（见 Step 3）。

## Step 3: 后端 — 持久化事件日志（EventStore）

**新文件**: `backend/web/services/event_store.py`（~80 行）

SQLite 表 `run_events`，复用 `~/.leon/leon.db`：

```sql
CREATE TABLE IF NOT EXISTS run_events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id  TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    event_type TEXT NOT NULL,
    data       TEXT NOT NULL,
    message_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_run_events_thread_run
ON run_events (thread_id, run_id, seq);
```

API：
- `append_event(thread_id, run_id, event, message_id) → seq`
- `read_events_after(thread_id, run_id, after_seq) → list[{seq, event, data}]`
- `get_latest_run_id(thread_id) → str | None`
- `cleanup_old_runs(thread_id, keep_latest=1) → deleted_count`
- `cleanup_thread(thread_id) → deleted_count`

## Step 4: 后端 — Producer 接入 EventStore

**文件**: `backend/web/services/streaming_service.py`

在 `_run_agent_to_buffer` 中：

1. 生成 `run_id = str(uuid.uuid4())`，存到 `buf.run_id`
2. 定义 `emit()` 闭包：`append_event(SQLite)` → 注入 `_seq`/`_run_id` → `buf.put()`
3. 所有 `await buf.put(...)` 替换为 `await emit(..., message_id=...)`
4. `finally` 中调 `cleanup_old_runs(thread_id, keep_latest=1)`

**文件**: `backend/web/services/event_buffer.py`（+2 行）

`RunEventBuffer` 加 `run_id: str = ""` 字段。

## Step 5: 后端 — observe 端点支持 `after` 参数 + SQLite 回放

**文件**: `backend/web/routers/threads.py`

`GET /{thread_id}/runs/stream?after=N`：

```python
buf = app.state.thread_event_buffers.get(thread_id)
if buf:
    return EventSourceResponse(observe_run_events(buf, after))
# 无 buffer（服务重启）→ 从 SQLite 回放
run_id = get_latest_run_id(thread_id)
if not run_id:
    return EventSourceResponse(_empty_done())
events = read_events_after(thread_id, run_id, after)
return EventSourceResponse(_replay_from_db(events))
```

**文件**: `backend/web/services/streaming_service.py`

`observe_run_events(buf, after=0)` — cursor 从 `after` 开始。

---

## Step 6: 前端 — 类型 + 快照映射

**文件**: `frontend/app/src/api.ts`

### 6a. 类型变更

```typescript
interface BackendMessage {
  id?: string;              // 新增：LangGraph UUID
  type: string;
  content: unknown;
  tool_calls?: unknown[];
  tool_call_id?: string | null;
}

interface AssistantTurn {
  id: string;               // = 第一条 AIMessage 的 UUID
  messageIds?: string[];    // 新增：该 turn 包含的所有 AIMessage UUID
  role: "assistant";
  segments: TurnSegment[];
  timestamp: number;
}

interface UserMessage {
  id: string;               // = HumanMessage 的 UUID
  role: "user";
  content: string;
  timestamp: number;
}
```

### 6b. `mapBackendEntries` 改造

核心变化：用 `msg.id` 作为 ID，`messageIds` 记录 turn 包含的所有 AIMessage UUID。

```
HumanMessage → entries.push({ id: msg.id, ... })，currentTurn = null
AIMessage（首条）→ turn = { id: msg.id, messageIds: [msg.id], ... }
AIMessage（后续，currentTurn 存在）→ currentTurn.messageIds.push(msg.id)
ToolMessage → 不变（用 tool_call_id 匹配）
```

### 6c. `observeRun` 加 `after` 参数

```typescript
function observeRun(threadId, onEvent, signal?, after?: number)
// → GET /runs/stream?after=N
```

## Step 7: 前端 — SSE 事件处理器用 `message_id` 匹配

**文件**: `frontend/app/src/hooks/stream-event-handlers.ts`

### 7a. `processStreamEvent` 提取 `message_id`

从 `event.data.message_id` 提取，传给各 handler。

### 7b. 去重规则（确定性）

Text 不需要去重——时序保证消除了竞态（见 Step 8b）。

| 事件类型 | 去重机制 |
|----------|----------|
| `text` | 不去重。时序保证：快照先加载完，SSE 后启动，不会重复写入 |
| `tool_call` | 如果 turn 的 segments 已有该 `tool_call_id` → skip |
| `tool_result` | 如果对应 tool segment 已有 `result` 且 `status=done` → skip |

### 7c. 多 AIMessage 处理

SSE 事件流中 `message_id` 变化 = 新的 AIMessage 开始。但都路由到同一个 `turnId`（第一条 AIMessage 的 UUID）。`messageIds` 数组记录所有已见的 message_id，用于去重判断。

## Step 8: 前端 — 重连逻辑

**文件**: `frontend/app/src/hooks/use-stream-handler.ts`

### 8a. `handleSendMessage`（发送新消息）

1. 创建临时 turn（`id = makeId("turn")`）→ 立刻显示头像框 + ThinkingIndicator
2. 第一个带 `message_id` 的 SSE 事件到达 → 重绑 `turn.id = message_id`，设 `messageIds = [message_id]`
3. 后续事件用稳定 `turnId` 匹配

### 8b. 重连 useEffect（threadId 变化 / mount）— 串行时序，消除竞态

```
1. await loadThread(threadId)     ← 骨架屏显示，等快照加载完
2. entries 就绪（稳定 ID）        ← 基线确立
3. getThreadRuntime()             ← 检查是否有 active run
4. if ACTIVE → observeRun()      ← 在基线之上做增量
5. SSE 事件的 message_id 匹配到快照里的 turn → 原地追加
```

关键：**`await loadThread` 完成后才启动 `observeRun`**。这是依赖关系，不是 hack——增量必须在基线之后。骨架屏是 `loadThread` 的自然 loading 状态。

不需要 text 去重：快照加载完后 SSE 才开始，不会重复写入已有文本。
Tool 去重：`tool_call_id` 精确匹配（快照里已有的 tool → skip）。

### 8c. `loadThread` 保持简单覆盖

**文件**: `frontend/app/src/hooks/use-thread-data.ts`

`loadThread` 不需要"智能合并"。因为：
- 发送消息时：`loadThread` 不会被调用（只有 SSE 在写 entries）
- 重连时：`loadThread` 先完成，`observeRun` 后启动，不存在并发写入
- 唯一调 `loadThread` 的时机是 threadId 变化，此时旧 entries 应该被完全替换

所以 `setEntries(mappedEntries)` 全量覆盖是正确的行为，不需要改。

---

## 改动文件汇总

| 文件 | 改动 | 行数估算 |
|------|------|----------|
| `backend/web/utils/serializers.py` | +`id` 字段 | +1 |
| `backend/web/services/event_store.py` | 新文件：SQLite 事件日志 | ~80 |
| `backend/web/services/event_buffer.py` | +`run_id` 字段 | +2 |
| `backend/web/services/streaming_service.py` | `emit()` 辅助 + `message_id` + `after` 参数 | ~25 |
| `backend/web/routers/threads.py` | observe 端点加 `after` + SQLite 回放 | ~15 |
| `frontend/app/src/api.ts` | 类型 + `mapBackendEntries` 用 msg.id + `observeRun` after | ~30 |
| `frontend/app/src/hooks/stream-event-handlers.ts` | `message_id` 提取 + tool 去重 | ~20 |
| `frontend/app/src/hooks/use-stream-handler.ts` | message_id 绑定 + 串行重连逻辑 | ~30 |
| **总计** | | **~205** |

注意：`use-thread-data.ts` 不需要改动。`loadThread` 的全量覆盖是正确行为。

## 数据流

### 场景 1：发送消息
```
用户发消息 → 创建临时 turn(id=turn-xxx)
→ POST /runs → 后端生成 run_id，agent 开始执行
→ 第一个 text 事件带 message_id(AIMessage UUID)
→ 前端重绑 turn.id = message_id
→ 后续事件用 message_id 匹配 → 追加 segments
→ 事件同步写入 SQLite(run_events)
→ done → 完成
```

### 场景 2：切换 thread 再切回
```
切走 → abort SSE（producer 不受影响）
切回 → loadThread 加载快照（entries 有稳定 messageId）
→ getThreadRuntime() = ACTIVE
→ observeRun() → SSE 回放事件
→ message_id 匹配到快照里的 turn → 去重过滤 → 只追加新内容
→ 实时跟踪
```

### 场景 3：刷新页面
```
同场景 2 — loadThread 快照 + observeRun 增量，messageId 做桥
```

### 场景 4：服务端重启
```
buffer 丢失 → observe 端点从 SQLite 回放
→ agent 状态 = IDLE（重启后无 active run）
→ 前端只看到快照，不触发 observeRun
→ 无数据丢失（checkpoint 有完整历史）
```

## 验证

1. 发消息 → DevTools Network 检查 SSE 事件有 `message_id` 和 `_seq`
2. 发消息 → 切换 thread → 切回 → 内容无丢失，无重复
3. 发消息 → 刷新页面 → 内容完整，如有 active run 则自动重连
4. 发消息 → kill 后端 → 重启 → 快照完整，`run_events` 表有记录
5. 侧边栏 running 旋转环正确显示/消失
6. 取消运行 → cancelled 事件正确处理
7. TUI runner 不受影响（`stream_agent_execution` 兼容包装）
8. `npx tsc --noEmit` 零错误，`npx vite build` 成功
