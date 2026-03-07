# Task #5/#6/#7 预研摘要

## Task #5 agent.py 集成关键点

### middleware 栈（6层，新增 ToolRunner）
顺序（list index，SpillBuffer 最后 insert(0)）：
1. SteeringMiddleware(queue_manager)
2. MemoryMiddleware(context_limit, pruning_config, compaction_config, db_path, summary_repo, checkpointer, verbose)
3. PromptCachingMiddleware(ttl="5m", min_messages_to_cache=0)
4. FileSystemMiddleware(workspace_root, max_file_size, allowed_extensions, hooks, enabled_tools, operation_recorder, backend=sandbox.fs(), verbose)
5. SearchMiddleware(workspace_root, max_file_size, verbose)
6. WebMiddleware(tavily_api_key, exa_api_key, firecrawl_api_key, jina_api_key, ...)
7. CommandMiddleware(workspace_root, default_timeout, hooks, enabled_tools, executor=sandbox.shell(), registry, queue_manager, verbose)
8. SkillsMiddleware(skill_paths, enabled_skills, verbose)
9. TodoMiddleware(verbose) — 待替换为 TaskService
10. TaskBoardMiddleware()
11. TaskMiddleware(workspace_root, parent_model, api_key, model_kwargs, queue_manager, verbose)
12. MonitorMiddleware(context_limit, model_name, verbose)
13. ToolRunner(registry=ToolRegistry, validator=ToolValidator) ← 新增最内层
→ SpillBufferMiddleware.insert(0) ← 最外层

### Post-init 注入（必须保留）
```python
self._task_middleware.set_parent_middleware(middleware)
self._task_middleware.set_db_path(self.db_path)
self._task_middleware.set_agent(self)
self._command_middleware.set_agent(self)
self._memory_middleware.set_runtime(self.runtime)
self._memory_middleware.set_model(self.model)
self._monitor_middleware.mark_ready()
```

### Placeholder Tool 陷阱
- `create_agent(tools=mcp_tools)` 接收 BaseTool 实例，NOT JSON schemas
- Middleware 注入 tool schemas 通过 wrap_model_call 的第二条路径
- 如果没有 BaseTool 会创建 placeholder，ToolRunner 不影响这个逻辑
- `_has_middleware_tools` 检查 middleware 是否有 .tools 属性（BaseTool）

### self._registry 接入点
- agent.py line 128: `self._registry = registry` 外部传入，通常 None
- line 947: CommandMiddleware 接收 `registry=getattr(self, "_registry", None)`
- 新架构：将 self._registry 替换为 ToolRegistry 实例

### 安全改造路径（不破坏现有功能）
1. 在 _build_middleware_stack 末尾 append ToolRunner（不是替换任何 middleware）
2. 将 self._registry 替换为 ToolRegistry 实例
3. 初始化 Services 并注册到 ToolRegistry
4. 保留原有 middleware 作为 fallback（gradual migration）
5. SpillBuffer 仍然 insert(0) 最外层

### tool_middleware_map 的真实位置
**在 core/task/subagent.py lines 91-187（不在 agent.py）**
SubagentRunner._build_subagent_middleware 中，用于过滤 parent middleware 给 sub-agent

## Task #6 import 路径变更清单

### agent.py 改动
| 行 | 旧 import | 新 import |
|---|-----------|-----------|
| 41 | from core.command import CommandMiddleware | from core.tools.command import CommandMiddleware |
| 44 | from core.spill_buffer import SpillBufferMiddleware | from core.runtime.middleware.spill_buffer import SpillBufferMiddleware |
| 47-50 | from core.command.hooks.* | from core.tools.command.hooks.* |
| 51 | from core.filesystem import FileSystemMiddleware | from core.tools.filesystem import FileSystemMiddleware |
| 52 | from core.memory import MemoryMiddleware | from core.runtime.middleware.memory import MemoryMiddleware |
| 54 | from core.monitor import MonitorMiddleware | from core.runtime.middleware.monitor import MonitorMiddleware |
| 55 | from core.prompt_caching import PromptCachingMiddleware | from core.runtime.middleware.prompt_caching import PromptCachingMiddleware |
| 56 | from core.queue import MessageQueueManager, SteeringMiddleware | from core.runtime.middleware.queue import MessageQueueManager, SteeringMiddleware |
| 57 | from core.search import SearchMiddleware | from core.tools.search import SearchMiddleware |
| 58 | from core.skills import SkillsMiddleware | from core.tools.skills import SkillsMiddleware |
| 61 | from core.todo import TodoMiddleware | 删除（替换为 TaskService） |
| 62 | from core.web import WebMiddleware | from core.tools.web import WebMiddleware |

### backend/web/ 改动
- services/streaming_service.py: from core.monitor import AgentState → from core.runtime.middleware.monitor import AgentState
- core/lifespan.py: from core.queue import → from core.runtime.middleware.queue import
- routers/threads.py: AgentState + format_steer_reminder → core.runtime.middleware.monitor/queue
- routers/workspace.py: from core.filesystem.local_backend import → from core.tools.filesystem.local_backend import

### tui/ 改动
- runner.py, app.py: AgentState → core.runtime.middleware.monitor; format_steer_reminder → core.runtime.middleware.queue

### core/task/subagent.py 改动
- CommandMiddleware, FileSystemMiddleware, SearchMiddleware, WebMiddleware → core.tools.*
- format_task_notification → from core.runtime.middleware.queue import

### 不需要动
- core/task/ (SubAgent 系统，独立，未迁移)

## Task #7 P2 Multi-Agent 关键点

### SubagentRunner 工作原理
1. 从 AgentConfig 获取 model/system_prompt/tools
2. _build_subagent_middleware 用 tool_middleware_map 从 parent middleware 过滤
3. 独立 SQLite checkpointer (~/.leon/subagents/{task_id}.db)
4. 同步/后台两种执行模式
5. 完成后通过 QueueManager.enqueue → wake handler 通知 parent

### QueueManager 核心 API
- enqueue(content, thread_id, notification_type) → INSERT + 触发 wake
- drain_all(thread_id) → 原子 pop 全部（SteeringMiddleware 用这个）
- register_wake(thread_id, handler) / unregister_wake
- 消息类型：steer, agent（可扩展 agent_message）

### P2 SendMessageService 设计
1. 查 AgentRegistry 获取 target agent 的 thread_id
2. QueueManager.enqueue(message, thread_id=target_thread_id, "agent_message")
3. Wake handler 自动唤醒 target
4. SteeringMiddleware.drain_all 自动注入

### P2 关键扩展点
- AgentRegistry: agent_id → thread_id 映射（新建 SQLite）
- sub-agent 必须有 SteeringMiddleware（当前被过滤掉了）
- sub-agent 需要注册 wake handler（当前没有）
- 消息格式：format_agent_message(from, content)

## Task #7 深度补充（SubagentRunner 实际机制）

### 关键发现：SubagentRunner 不创建 LeonAgent
它直接调用 `create_agent(model, tools, system_prompt, middleware, checkpointer)`
- middleware 是从 parent 过滤出的子集（只有 FS/Search/Command/Web）
- 独立 SQLite checkpointer per task
- **SteeringMiddleware 没有在 sub-agent 中**

### P2 建议路径：轻量扩展（不是全新 LeonAgent）
在 SubagentRunner 基础上扩展，加：
1. AgentRegistry（name → thread_id 映射，SQLite）
2. sub-agent 的 middleware 中加入 SteeringMiddleware
3. SendMessageService 通过 QueueManager 路由消息

### AgentService 最小参数集
`model_name`, `api_key`, `workspace_root`, `queue_manager`, `registry`

### BackgroundTaskRegistry API（core/task/registry.py）
- `register(entry: TaskEntry)`, `update(task_id, **kwargs)`, `get(task_id)`, `list_by_thread(thread_id)`, `cleanup_thread`
- TaskEntry: task_type ("bash"|"agent"), status, text_buffer, result
