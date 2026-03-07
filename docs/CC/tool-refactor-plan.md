# Leon Tool 架构重建方案

## Context

**为什么做：**
Leon 当前 tool 系统存在三个问题：
1. **无统一错误规范**：每个 middleware 自己处理错误，格式不一致
2. **无 inline/deferred 区分**：所有 tool schema 在每次 model call 时全量注入，无法延迟加载
3. **无中心 ToolRegistry**：tool 的 schema、mode、handler 分散在各 middleware，无法统一管理

**目标：** 对齐 Claude Code 的精华设计，对 Leon 进行架构级重建——明确分层（runtime / tools / agents），建立中心 ToolRegistry，实现真正的多 Agent 对等架构。

---

## 方案概览

三个阶段：

```
P0  三层错误规范（1-2天）
P1  ToolRegistry + ToolRunner + Middleware→Service 降级（3-4天）
P2  Multi-Agent 架构（独立 Agent + 消息通信 + Team 协调）
```

### Middleware 职责重新划分

**核心原则：** Middleware 必须拦截调用链（修改 request 或观测结果）。只提供工具实现的，降级为 Service。

**保留为 Middleware（6 个，含 1 个新增）：**

| Middleware | 为什么必须在调用链上 |
|---|---|
| SpillBufferMiddleware | 最外层，拦截所有 tool_call 结果检查大小 |
| MonitorMiddleware | 观测 model_call token 消耗 |
| PromptCachingMiddleware | 修改 request（加 cache_control 标记） |
| MemoryMiddleware | model_call 前修改上下文（pruning/compaction） |
| SteeringMiddleware | model_call 前注入 queue 消息（含跨 Agent 消息） |
| **ToolRunner** *(新增)* | 最内层，所有注册 tool 的唯一分发点 |

Middleware 栈顺序（外→内）：

```
SpillBufferMiddleware
  MonitorMiddleware
    PromptCachingMiddleware
      MemoryMiddleware
        SteeringMiddleware
          ToolRunner      ← 调用链终点，处理所有注册 tool
```

**降级为 Service（8 个）：**

| 原 Middleware | Service | tool mode 默认 | 特殊注意 |
|---|---|---|---|
| FileSystemMiddleware | FileSystemService | inline | — |
| SearchMiddleware | SearchService | inline | — |
| WebMiddleware | WebService | inline | 含 async handler（AI 提取） |
| CommandMiddleware | CommandService | inline | `_registry`/`_queue_manager` 内化为 Service 状态 |
| SkillsMiddleware | SkillsService | inline | **schema 动态**：每次查询重新扫描 skills index |
| TodoMiddleware | **TaskService** | **deferred** | SQLite 共享，同 thread 下所有 Agent 可见，对齐 CC Task 语义 |
| TaskBoardMiddleware | — | — | **本次不动**：独立的用户定时任务功能，设计未稳定 |
| TaskMiddleware | **AgentService** | inline | Agent/TaskOutput/TaskStop，**SubagentRunner 删除**，职责并入 AgentService |
| *(新增)* | ToolSearchService | inline | handler 直接访问 ToolRegistry.search() |

Service 只做两件事：初始化时向 ToolRegistry 注册（schema + handler + mode），提供 handler 实现。不实现任何 AgentMiddleware 接口。

---

## P0：三层错误规范

### 当前问题

各 middleware 错误处理方式不统一，有的返回文本，有的 raise，有的返回 None。

### 目标

对齐 CC 分析的三层语义：

| 层级 | 语义 | 格式 |
|------|------|------|
| Layer 1 | 参数校验失败（schema 不通过） | `InputValidationError: {tool} failed: ...` |
| Layer 2 | 执行失败（handler 抛异常） | `<tool_use_error>...</tool_use_error>` |
| Layer 3 | 软性失败（找不到/为空） | 纯文本，不包标签 |

### 实现

**新增文件：`core/runtime/runner.py`**

```python
class ToolRunner:
    """统一 Tool 调用出口，负责错误 normalize。

    各 middleware handler 只管 raise，不管格式。
    """

    def run(self, tool_name: str, handler: Callable, args: dict) -> str:
        try:
            result = handler(**args)
            return result  # Layer 3：handler 自己返回软性失败文本
        except InputValidationError as e:
            # Layer 1：参数错误
            return f"InputValidationError: {tool_name} failed: {e}"
        except Exception as e:
            # Layer 2：执行错误
            return f"<tool_use_error>{e}</tool_use_error>"
```

**改动范围：** 所有 middleware 的 `wrap_tool_call()` 出口统一走 ToolRunner，handler 内部不再包装错误格式。

---

## P1：ToolRegistry + inline/deferred 模式

### 核心设计

```python
class ToolMode(Enum):
    INLINE   = "inline"    # schema 注入 system prompt / 每次 model call
    DEFERRED = "deferred"  # 仅通过 tool_search 发现
```

**新增文件：`core/runtime/registry.py`**

```python
Handler = Callable[..., str] | Callable[..., Awaitable[str]]
SchemaProvider = dict | Callable[[], dict]   # 支持动态 schema（SkillsService 需要）

@dataclass
class ToolEntry:
    name: str
    mode: ToolMode
    schema: SchemaProvider          # 静态 dict 或动态 callable（每次调用重新生成）
    handler: Handler                # 同步或异步 callable
    source: str                     # 来源 Service 名称，用于调试

    def get_schema(self) -> dict:
        return self.schema() if callable(self.schema) else self.schema

class ToolRegistry:
    def register(self, entry: ToolEntry) -> None: ...
    def get_inline_schemas(self) -> list[dict]: ...          # 供 ToolRunner.wrap_model_call 注入
    def search(self, query: str) -> list[ToolEntry]: ...     # 供 tool_search 查询（返回全部，含 inline）
    def get(self, name: str) -> ToolEntry | None: ...        # 供 ToolRunner 分发
```

### ToolRegistry 位置

由 `core/runtime/agent.py` 创建并持有，初始化各 Service 时作为依赖注入。这样：
- 依赖关系清晰（agent 是 registry 的 owner）
- middleware 无需感知彼此
- 不引入全局单例

### tool_search 工具

不再是独立 Middleware，改为 **ToolSearchService** 向 ToolRegistry 注册：

```python
class ToolSearchService:
    def __init__(self, registry: ToolRegistry):
        registry.register(ToolEntry(
            name="tool_search",
            mode=ToolMode.INLINE,
            schema={"name": "tool_search", "parameters": {"query": {"type": "string"}}},
            handler=self._search,
            source="ToolSearchService"
        ))

    def _search(self, query: str) -> str:
        results = self.registry.search(query)
        return json.dumps([e.get_schema() for e in results], indent=2)
```

### ToolRunner（核心新增）

替代原来 7 个 "伪 Middleware" 的全部分发逻辑，支持 sync/async handler：

```python
class ToolRunner(AgentMiddleware):
    def __init__(self, registry: ToolRegistry, validator: ToolValidator):
        self.registry = registry
        self.validator = validator

    def wrap_model_call(self, request, handler):
        # 注入 inline schemas
        inline_schemas = self.registry.get_inline_schemas()
        tools = list(request.tools or []) + inline_schemas
        return handler(request.override(tools=tools))

    def wrap_tool_call(self, request, handler):
        name = request.tool_call["name"]
        args = request.tool_call["args"]

        entry = self.registry.get(name)
        if entry is None:
            return handler(request)   # 不是注册 tool，继续向上传（如 MCP tools）

        try:
            self.validator.validate(entry.get_schema(), args)
        except InputValidationError as e:
            return ToolMessage(content=f"InputValidationError: {name} failed:\n{e}")

        try:
            result = entry.handler(**args)
            if asyncio.iscoroutine(result):
                result = asyncio.get_event_loop().run_until_complete(result)
            return ToolMessage(content=result)
        except Exception as e:
            return ToolMessage(content=f"<tool_use_error>{e}</tool_use_error>")

    async def awrap_tool_call(self, request, handler):
        # 同逻辑，但 await handler
        ...
```

**Agent 工具配置**（原 tool_middleware_map 机制完全废弃）：

新架构中每个 LeonAgent 根据 `AgentConfig.tools` 列表，在自身初始化时只加载对应的 Service：
- `AgentConfig.tools: ["*"]` → 加载所有 Service
- `AgentConfig.tools: ["Read", "Grep"]` → 只加载 FileSystemService + SearchService
- 无需 `tool_middleware_map`，ToolRegistry 自动管理

### 模式可配置（对齐 config 系统）

**`config/defaults/tools.json` 新增：**

```json
{
  "tool_modes": {
    "TaskCreate": "deferred",
    "TaskUpdate": "deferred",
    "TaskGet":    "deferred",
    "TaskList":   "deferred",
    "Read":       "inline",
    "Bash":       "inline",
    "Grep":       "inline",
    "Glob":       "inline",
    "tool_search": "inline"
  }
}
```

切换只需改 JSON，无需改代码。

### 两个实现细节决策

**Timeout 单位转换边界**

- Schema/接口层（LLM 调用）：毫秒（ms）
- 内部实现层（asyncio.wait_for 等）：秒（s）
- 转换发生在 handler 入口：`timeout_s = timeout_ms / 1000`
- 不允许在其他地方转换，避免 bug 扩散

**AgentConfig.tools 过滤机制（方案 B）**

所有 Service 都初始化，ToolRegistry 按 AgentConfig.tools 白名单过滤注册：

```python
class ToolRegistry:
    def register(self, entry: ToolEntry, allowed_tools: set[str] | None = None) -> None:
        if allowed_tools is not None and entry.name not in allowed_tools:
            return  # 静默跳过，不注册
        self._tools[entry.name] = entry
```

LeonAgent 初始化时：
1. 创建 ToolRegistry（传入 `allowed_tools` 白名单）
2. 初始化所有 Service（Service 向 ToolRegistry 注册，被过滤的工具静默跳过）
3. `AgentConfig.tools: ["*"]` → `allowed_tools=None`（不过滤）

---



**新架构中，各 middleware 不再各自注入 tool schemas。**

ToolRunner 统一负责：
- `wrap_model_call`：调用 `registry.get_inline_schemas()` 注入所有 inline tools
- 各 middleware 的 `wrap_model_call` 只做自己的横切关注点（cache_control、pruning 等），不再处理 tool 注入

---

## P2：Multi-Agent 架构

### 核心观念转变

**Leon 里不再有"子 Agent"概念，只有 Agent。** 所有 Agent 都是独立的一等公民，拥有各自完整的 ToolRegistry + Services + Middleware 栈。当前 SubagentRunner 创建轻量 LangChain agents（共享父 middleware）的方式，改为创建真正独立的 **LeonAgent 实例**。

Agent 之间的关系是**平等的 peer 通信**（SendMessage），而不是父子委派。

---

### Layer 1：独立 Agent 实例

**SubagentRunner 不再需要，职责并入 AgentService**

原 SubagentRunner 的四个职责重新归属：
- 创建 LangChain agent → **LeonAgent 自身初始化**（完整独立实例）
- 后台任务管理 → **AgentService**（asyncio.create_task + shield）
- 流式事件路由 → **EventBus**（backend 层）
- task 追踪 → **AgentRegistry**（SQLite）

**AgentService 核心逻辑**：

```python
class AgentService:
    async def _spawn_agent(self, params: AgentParams) -> str:
        agent = LeonAgent(
            model_name=params.model,
            workspace_root=self.workspace_root,
            subagent_type=params.subagent_type,  # → AgentConfig 确定 tools/prompt
            queue_manager=self.shared_queue_manager,  # SendMessage 路由
            event_bus=self.event_bus,            # 注入 EventBus
            agent_registry=self.agent_registry,  # 共享注册表
        )
        task = asyncio.create_task(agent.run(params.prompt))

        entry = AgentEntry(name=params.name, thread_id=agent.thread_id, status="running")
        self.agent_registry.register(entry)

        if params.run_in_background:
            return json.dumps({"task_id": entry.agent_id, "status": "running"})

        # 隐式切后台（shield + timeout）
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=params.timeout)
        except asyncio.TimeoutError:
            return json.dumps({"task_id": entry.agent_id, "status": "backgrounded"})
```

**AgentRegistry**（新增 `core/agents/registry.py`，SQLite 持久化）：

```python
@dataclass
class AgentEntry:
    agent_id: str
    name: str              # 用户指定名，用于 SendMessage 路由
    thread_id: str
    status: str            # "running" | "completed" | "error"
    parent_agent_id: str | None

class AgentRegistry:
    def register(self, entry: AgentEntry) -> None: ...
    def get_by_name(self, name: str) -> AgentEntry | None: ...
    def get_by_id(self, agent_id: str) -> AgentEntry | None: ...
    def update_status(self, agent_id: str, status: str) -> None: ...
```

持久化路径：`~/.leon/agent_registry.db`

---

### Layer 2：Agent 间消息通信

**QueueManager 已有 SQLite queue + wake handlers，直接扩展：**

新增 **SendMessageService**（`core/agents/communication/`）：

```python
class SendMessageService:
    def __init__(self, registry: ToolRegistry, agent_registry: AgentRegistry, queue_manager: QueueManager):
        # 注册 SendMessage 工具（inline mode，所有 Agent 默认拥有）

    def _send(self, type: str, content: str, recipient: str | None, summary: str | None,
              request_id: str | None, approve: bool | None) -> str:
        if type in ["message", "shutdown_request"]:
            entry = self.agent_registry.get_by_name(recipient)
            # enqueue 到目标 Agent 的 thread_id
            # wake_handler 立即唤醒空闲 Agent（已有机制）
        elif type == "broadcast":
            # enqueue 给所有 running Agent
```

**SteeringMiddleware 无需改动**：已有 `before_model` hook，drain 队列后注入 HumanMessage。

---

### Layer 3：Team 协调层

新增 **TeamService**（`core/agents/teams/`，deferred mode）：

| Tool | 功能 |
|---|---|
| `TeamCreate` | 创建命名 Agent 组，设定 team_id，成员自动进组 |
| `TeamDelete` | 解散 team，清理成员关联 |

**TaskService 共享**：同 thread/team 下所有 Agent 通过 TaskCreate/TaskList/TaskUpdate/TaskGet 共享同一套 Task 列表（SQLite，对齐 CC Task 语义）。

---

### 与 CC 对齐

| CC tool | Leon 对应 | Service |
|---|---|---|
| `Agent`（spawn）| `Agent` tool（含 `name` 参数） | AgentService |
| `TaskOutput` / `TaskStop` | 同名 tool | AgentService |
| `SendMessage` | 同名 tool（type/recipient/content） | SendMessageService |
| `TeamCreate` / `TeamDelete` | 同名 tool | TeamService |
| `TaskCreate/Update/List/Get` | 同名 tool | TaskService（deferred，SQLite 共享） |

### Agent tool 对齐 CC 参数

| 参数 | 原 Leon | 新（对齐 CC） |
|---|---|---|
| agent 名称 | `SubagentType` | `subagent_type` |
| 提示词 | `Prompt` | `prompt` |
| 命名 | — | `name`（新增，用于 SendMessage 路由） |
| 描述 | `Description` | `description` |
| 后台运行 | `RunInBackground` | `run_in_background` |
| 恢复 | `Resume` | `resume` |
| 最大轮次 | `MaxTurns` | `max_turns` |

---

### 三阶段校验（对齐 CC 实验结论）

**新增：`core/runtime/validator.py`**

```python
class ToolValidator:
    def validate(self, schema: dict, args: dict) -> ValidationResult:
        # Phase 1: required 字段检查（快速 fail，人类可读）
        missing = [f for f in schema.get("required", []) if f not in args]
        if missing:
            msgs = [f"The required parameter `{f}` is missing" for f in missing]
            raise InputValidationError("\n".join(msgs))

        # Phase 2: 类型检查（人类可读）
        for name, val in args.items():
            prop = schema["properties"].get(name, {})
            expected = prop.get("type")
            if expected and not self._type_matches(val, expected):
                actual = type(val).__name__
                raise InputValidationError(
                    f"The parameter `{name}` type is expected as `{expected}` but provided as `{actual}`"
                )

        # Phase 3: enum / union 校验（返回 JSON 结构）
        issues = self._validate_enum_union(schema, args)
        if issues:
            raise InputValidationError(json.dumps(issues))

        return ValidationResult(ok=True, params=args)
```

**与 ToolRunner 集成：**

```python
class ToolRunner:
    def run(self, name: str, schema: dict, handler: Callable, args: dict) -> str:
        # 校验先行
        try:
            self.validator.validate(schema, args)
        except InputValidationError as e:
            return f"InputValidationError: {name} failed due to the following issue:\n{e}"

        # 执行
        try:
            return handler(**args)
        except Exception as e:
            return f"<tool_use_error>{e}</tool_use_error>"
```

---

## 隐式异步切换（Sync-to-Async）

### 机制

利用 `asyncio.shield()` + `wait_for()` 实现"运行中无感切后台"：

```python
# CommandService 和 AgentService 共用此模式
task = asyncio.create_task(actual_work())

if run_in_background:
    task_id = registry.register(task)
    return json.dumps({"task_id": task_id, "status": "running"})

try:
    result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout_seconds)
    return result
except asyncio.TimeoutError:
    # 超时但 task 仍在运行（shield 保护），无感切后台
    task_id = registry.register(task)
    return json.dumps({"task_id": task_id, "status": "backgrounded",
                       "message": "Still running, use TaskOutput to get result"})
```

**关键**：`asyncio.shield()` 保证外层超时取消时，内层 task 不被 cancel，继续运行。

### 应用范围

- **CommandService**（`Bash`）：`timeout` 参数（毫秒，默认 120000ms）；超时从"报错"改为"自动后台"
- **AgentService**（`Agent` tool）：同样支持，`max_turns` 达限或超时自动后台

### 用户主动切后台

新增 API 接口（前端可调用）：

```
POST /api/tasks/{task_id}/background
```

将正在运行的同步任务切换为后台模式（立即返回，不再等待）。

`TaskOutput` / `TaskStop` 两个 tool 对所有任务类型（命令、Agent）统一适用。

---

## P2 事件流架构（共享 EventBus）

### 问题

P2 中 Agent 成为独立 LeonAgent 实例，当前"通过父 runtime 转发子 Agent 事件"的路径不再可用。

### 方案：进程级 EventBus（后端层）

```
Agent A ─┐
Agent B ─┼─→ EventBus（backend/，按 agent_id 路由）─→ SSE ─→ 前端
Agent C ─┘
```

**层次划分**：
- **Core**：`LeonAgent` 只持有抽象的 `emit(event)` 回调（或 Protocol），不感知 SSE
- **Backend**：`backend/web/event_bus.py` 实现具体的 EventBus，注入到 LeonAgent 构造器
- 前端维持一条 SSE 连接，按 `agent_id` / `thread_id` 过滤事件，UI 分 tab 渲染各 Agent 输出

---

## 目录结构重组

### 新结构

```
core/                      # Leon 核心系统（三层）
  runtime/                 # 执行引擎（原根目录 agent.py + core/memory|monitor|queue|spill_buffer）
    agent.py               # LeonAgent 主类
    registry.py            # ToolRegistry
    runner.py              # ToolRunner（最内层 Middleware）
    validator.py           # ToolValidator
    middleware/            # 调用链拦截器
      memory/              # MemoryMiddleware
      monitor/             # MonitorMiddleware
      queue/               # SteeringMiddleware
      spill_buffer/        # SpillBufferMiddleware
      prompt_caching/      # PromptCachingMiddleware

  tools/                   # 工具实现（向 ToolRegistry 注册）
    filesystem/            # FileSystemService（原 core/filesystem/）
    command/               # CommandService（原 core/command/），支持隐式后台
    search/                # SearchService（原 core/search.py）
    web/                   # WebService（原 core/web/）
    skills/                # SkillsService（原 core/skills/），动态 schema
    task/                  # TaskService（原 core/todo/，改名），SQLite 共享
    tool_search/           # ToolSearchService（新增）

  agents/                  # 多 Agent 协调（高于单 Agent 层次）
    registry.py            # AgentRegistry（SQLite 持久化）
    service.py             # AgentService（Agent/TaskOutput/TaskStop）
    communication/         # SendMessageService
    teams/                 # TeamService（TeamCreate/TeamDelete）

sandbox/                   # 执行环境（不动）
storage/                   # 存储 providers（不动）
config/                    # 配置系统（不动）
backend/                   # FastAPI + EventBus（新增 event_bus.py）
  taskboard/               # Board 功能（从 core/taskboard/ 迁移，逻辑不变）
frontend/                  # React UI（不动）
```

### 命名逻辑

| 目录 | 为什么这个名字 |
|------|-------------|
| `core/` | 父容器，Leon 核心系统的三层结构 |
| `core/runtime/` | 执行运行时，不说"重要"只说用途 |
| `core/tools/` | 直接对应领域词汇 tool |
| `core/agents/` | 多 Agent 协调，区别于 LeonAgent 类本身 |

---

## 关键文件改动一览

| 文件/目录 | 改动类型 | 说明 |
|------|--------|------|
| `core/runtime/agent.py` | **迁移**（原根目录 `agent.py`） | LeonAgent 主类，构建 6-middleware 栈，初始化 ToolRegistry + Services |
| `core/runtime/registry.py` | **新增** | ToolRegistry + ToolEntry + ToolMode |
| `core/runtime/runner.py` | **新增** | ToolRunner（最内层 Middleware），错误 normalize |
| `core/runtime/validator.py` | **新增** | 三阶段校验 |
| `core/runtime/middleware/memory/` | **迁移**（原 `core/memory/`） | MemoryMiddleware |
| `core/runtime/middleware/monitor/` | **迁移**（原 `core/monitor/`） | MonitorMiddleware |
| `core/runtime/middleware/queue/` | **迁移**（原 `core/queue/`） | SteeringMiddleware |
| `core/runtime/middleware/spill_buffer/` | **迁移**（原 `core/spill_buffer/`） | SpillBufferMiddleware |
| `core/tools/filesystem/` | **迁移+重构**（原 `core/filesystem/`） | FileSystemService |
| `core/tools/search/` | **迁移+重构**（原 `core/search.py`） | SearchService |
| `core/tools/command/` | **迁移+重构**（原 `core/command/`） | CommandService，支持隐式后台切换 |
| `core/tools/web/` | **迁移+重构**（原 `core/web/`） | WebService |
| `core/tools/skills/` | **迁移+重构**（原 `core/skills/`） | SkillsService，动态 schema |
| `core/tools/task/` | **新增**（原 `core/todo/`，改名） | TaskService，SQLite 共享 |
| `core/tools/tool_search/` | **新增** | ToolSearchService |
| `core/agents/registry.py` | **新增** | AgentRegistry，SQLite（`~/.leon/agent_registry.db`） |
| `core/agents/service.py` | **新增** | AgentService（Agent/TaskOutput/TaskStop），隐式后台切换 |
| `core/agents/communication/` | **新增** | SendMessageService，peer 通信路由 |
| `core/agents/teams/` | **新增** | TeamService，TeamCreate/TeamDelete |
| `backend/web/event_bus.py` | **新增** | 进程级 EventBus，runtime 只持有抽象 emit 回调 |
| `config/defaults/tools.json` | **修改** | 新增 tool_modes 字段 |
| `config/schema.py` | **修改** | ToolsConfig 新增 tool_modes |
| `core/task/` | **删除** | TaskMiddleware + SubagentRunner，职责已分散到新架构 |
| `core/todo/` | **删除** | 迁移到 `tools/task/` |
| `core/taskboard/` | **迁移**（移到 `backend/taskboard/`） | Board 是后端功能，不在 core 层；本次只移位置，不改逻辑 |

---

## 不改的部分

- **Sandbox 层接口不变**：FileSystemBackend / BaseExecutor 等 Capability 接口保持原样，只是引用方从 Middleware 改为 Service
- **Middleware 逻辑不变**：Memory / Monitor / SpillBuffer / Steering / PromptCaching 的代码逻辑不动，只是迁移目录到 `core/runtime/middleware/`
- **Config 系统不变**：只新增 `tool_modes` 字段

**删除**：
- `core/task/`（TaskMiddleware + SubagentRunner）：职责分散到 `core/agents/`、EventBus、LeonAgent 自身
- `core/todo/`：迁移为 `core/tools/task/`（TaskService，改名）

**迁移（逻辑不变，只移位置）**：
- `core/taskboard/` → `backend/taskboard/`（Board 是后端功能）

**Import 路径变更（批量更新，不涉及逻辑）**：
- `from agent import LeonAgent` → `from core.runtime.agent import LeonAgent`（影响：`backend/web/main.py`、`tui/`）
- `from core.memory import ...` → `from core.runtime.middleware.memory import ...`（及其他 middleware）
- `from core.filesystem.middleware import FileSystemMiddleware` → `from core.tools.filesystem.service import FileSystemService`（及其他 Service）
- `from core.taskboard import ...` → `from backend.taskboard import ...`

---

## 工具名 & 参数对齐（P1 同步完成）

### 工具重命名

| 原 Leon 名 | 新名（对齐 CC） | 说明 |
|---|---|---|
| `read_file` | `Read` | — |
| `write_file` | `Write` | — |
| `edit_file` | `Edit` | 同时补 `replace_all` 参数 |
| `multi_edit` | `multi_edit` | Leon 独有，保留 |
| `list_dir` | `list_dir` | Leon 独有，保留 |
| `run_command` | `Bash` | 见参数变更 |
| `command_status` | **删除** | 统一改用 `TaskOutput` |
| `web_search` | `WebSearch` | — |
| `Fetch` | `WebFetch` | — |
| `Task`（Agent 启动）| `Agent` | 参数已对齐，见 P2 |
| `TaskOutput` | `TaskOutput` | 已对齐 |
| `TaskCreate/Get/List/Update` | 同名 | 已对齐 |

### Bash 参数变更（原 run_command）

| 原参数 | 新参数 | 变更说明 |
|---|---|---|
| `CommandLine: str` | `command: str` | snake_case |
| `Blocking: bool = True` | `run_in_background: bool = False` | 语义取反，默认同步 |
| `Timeout: int`（秒）| `timeout: int`（毫秒）| 单位对齐 CC |
| `Cwd: str` | **删除** | CC 不暴露工作目录 |

### 参数命名约定变更

所有工具参数从 PascalCase 改为 snake_case，对齐 CC 标准。

同时更新 `conventions.md`：
> **工具参数**：snake_case（file_path, run_in_background）

---

## 验证方式

1. **P0 验证**：故意传错参数给 `Read`，确认返回格式符合三层规范
2. **P1 验证**：启动 agent，`TaskCreate` 不出现在 system prompt；调用 `tool_search("task")` 能返回 TaskCreate schema；之后可正常调用 TaskCreate
3. **异步切换验证**：启动长命令（`Bash`），到 timeout 后确认收到 `task_id`（非报错）；`TaskOutput(task_id)` 能拿到最终结果
4. **P2 验证**：
   - `Agent` tool 启动命名 Agent，再用 `SendMessage` 发消息，确认目标 Agent 收到并唤醒
   - 多个独立 Agent 事件都出现在同一 SSE 流里，前端按 agent_id 正确分 tab
   - `TeamCreate` 后，team 内两个 Agent 读写同一 TaskService 的 task
   - 复用 `docs/CC/tool_schemas/error/error.json` 中的 20+ 场景做回归测试
