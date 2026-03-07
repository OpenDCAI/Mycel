# 对齐报告

Generated: 2026-03-07

## 已对齐

### 核心架构文件
- `core/runtime/registry.py` — ToolRegistry, ToolEntry, ToolMode(INLINE/DEFERRED)
- `core/runtime/runner.py` — ToolRunner (AgentMiddleware, innermost layer)
- `core/runtime/validator.py` — ToolValidator (3-phase validation)
- `core/runtime/errors.py` — InputValidationError

### Middleware 迁移 (core/runtime/middleware/)
- `memory/` — MemoryMiddleware (pruning + compaction)
- `monitor/` — MonitorMiddleware, AgentState, AgentRuntime, apply_usage_patches
- `queue/` — MessageQueueManager, SteeringMiddleware, format_steer_reminder, format_task_notification
- `spill_buffer/` — SpillBufferMiddleware
- `prompt_caching/` — PromptCachingMiddleware

### Tool Services (core/tools/)
| Service | File | Tools | Mode |
|---------|------|-------|------|
| FileSystemService | filesystem/service.py | Read, Write, Edit, multi_edit, list_dir | INLINE |
| SearchService | search/service.py | Grep, Glob | INLINE |
| WebService | web/service.py | WebSearch, WebFetch | INLINE |
| CommandService | command/service.py | Bash | INLINE |
| SkillsService | skills/service.py | load_skill | INLINE |
| TaskService | task/service.py | TaskCreate, TaskGet, TaskList, TaskUpdate | DEFERRED |
| ToolSearchService | tool_search/service.py | tool_search | INLINE |

Total: 15 tools (11 inline, 4 deferred) — SkillsService adds 1 more when skill_paths configured

### P2 Multi-Agent (core/agents/)
- `registry.py` — AgentRegistry
- `service.py` — AgentService
- `communication/service.py` — SendMessageService
- `teams/service.py` — TeamService

### agent.py 集成
- ToolRegistry 初始化: `self._tool_registry = ToolRegistry()`
- Services 初始化: `self._init_services()` (全部 7 个 Service)
- ToolRunner 位置: middleware 栈第 12 层（Monitor 之后，SpillBuffer insert(0) 之前）
- 旧 middleware 保留: gradual migration 策略，新旧并行

### Bash 参数对齐 (CC 兼容)
- `command` (was CommandLine)
- `run_in_background` (was Blocking, semantics inverted)
- `timeout` in milliseconds (was seconds)
- `Cwd` removed

### Import 路径修复 (8 files, 11 locations)
- agent.py: 5 middleware imports updated
- backend/web/: 3 files updated (streaming_service, lifespan, threads)
- tui/: 2 files updated (runner, app)
- core/task/subagent.py: 1 queue import updated
- core/command/middleware.py: 1 queue formatter import updated
- No stale imports remain in updated files

### Config
- `config/schema.py`: ToolsConfig has `tool_modes: dict[str, str]`
- `config/defaults/tools.json`: 19 tool_modes entries (4 deferred, 15 inline)

### Import 验证
21/21 imports pass: all new modules importable

## 部分偏差

### 旧目录未删除
以下旧目录仍存在（backward-compat re-exports）:
- `core/monitor/`, `core/queue/`, `core/memory/`, `core/spill_buffer/`, `core/prompt_caching/`
- `core/filesystem/`, `core/search/`, `core/web/`, `core/command/`, `core/skills/`, `core/todo/`

这些是实际实现模块，`core/tools/*/service.py` 是薄包装层引用它们。完全迁移需要将实现也移到新路径，但当前阶段保留 backward-compat 是正确的。

### core/__init__.py 未更新
仍从旧路径 re-export，但因为旧模块仍存在，不影响功能。

### 测试文件未更新
`tests/` 目录下的 import 仍指向旧路径，依赖 backward-compat。

## 未实现

### 旧 middleware 移除 (Phase 2)
当前采用 gradual migration，新旧并行。完整移除需要：
1. 验证 ToolRunner 完全覆盖所有旧 middleware 的 tool call 路由
2. 从 `_build_middleware_stack` 中移除 FileSystemMiddleware, SearchMiddleware, WebMiddleware, CommandMiddleware, SkillsMiddleware, TodoMiddleware
3. 更新 SubagentRunner 的 `_build_subagent_middleware` 中的 tool_middleware_map

### tool_middleware_map 重构 (core/task/subagent.py)
SubagentRunner 仍用旧的 middleware class 映射来构建 sub-agent 栈。新架构应改为从 ToolRegistry 按 tool name 过滤。

## 建议补救

1. **Phase 2 移除旧 middleware**: 在 E2E 测试通过后，逐步移除旧 tool-bearing middleware
2. **SubagentRunner 迁移**: 改用 ToolRegistry 子集替代 tool_middleware_map
3. **测试文件批量更新**: `sed` 批量替换 `tests/` 中的旧 import 路径
4. **core/__init__.py 清理**: 清空或改为从新路径 re-export
