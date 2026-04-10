---
title: Runtime Web Subagent Shutdown Ownership
owner: fjj
priority: P1
status: done
created: 2026-04-09
---

# Runtime Web Subagent Shutdown Ownership

目标：把 web subagent 在 run complete 之后的 ownership 收回到正确层，不再让 completed child `LeonAgent` 实例因为 thread surface 还要可读，就继续挂在 `agent_pool` 里活到 app shutdown。

## CC analogue

- direct analogue: partial
- `Claude Code / cc-src` 保留的是可复用的 task / transcript / metadata truth
- `Claude Code / cc-src` 不是靠 completed subagent instance 常驻内存来实现复用

## Root Cause

当前 live seam 已经继续压深，不再只是“run-complete owner split”。

第一层 wrong-owner split 仍然成立：

1. `core/agents/service.py:_run_agent(... finally)` 在 web path 下明确跳过 `child_agent.close()`
2. `backend/web/services/streaming_service.py:run_child_thread_live(...)` 又把 child agent 挂进 `app.state.agent_pool`
3. child run 结束后，task surface 会完成、runtime 会回到 idle，但 child `LeonAgent` 实例继续留在 pool 里

但 fresh caller-proof 已经证明：即使 child run complete 后 close + detach，`SIGTERM` 下 patched backend 仍然不退出。

更深的 root cause 是：

1. 主 thread 的 web agent 通过 `asyncio.to_thread(create_agent_sync, ...)` 创建
   - `CleanupRegistry()` 在 worker thread 里拿不到当前 event loop
   - 所以普通 thread agent 不会注册 process signal handler
2. web subagent child 在 `core/agents/service.py:_run_agent(...)` 里直接在主 event loop 中 `self._child_agent_factory(...)`
3. `core/runtime/cleanup.py:CleanupRegistry.__init__()` 当前会立刻 `_setup_signal_handlers()`
4. 于是 child `LeonAgent` 的 `CleanupRegistry` 会在主 event loop 上注册 `SIGINT/SIGTERM/SIGHUP`
5. 这把 process signal owner 错误地下沉成了 per-agent cleanup object

所以这条 seam 的更准确表述已经变成：

- completed child instance 过度持久是第一层问题
- 真正把 `SIGTERM graceful shutdown` 打坏的，是 **per-agent CleanupRegistry 越权成了 process signal owner**

这也和 `Claude Code` 更一致地对上了：`cc-src` 的 cleanup registry 是 global cleanup function registry，本身不拥有 process signal。

## Implemented Slice

当前分成两步收口：

### Slice A: web child run-complete ownership

- `backend/web/services/streaming_service.py`
  - `run_child_thread_live(...)` 在完成后负责：
    - 从 `app.state.agent_pool` detach child
    - `agent.close(cleanup_sandbox=False)`
- `core/agents/service.py`
  - 只更新注释，明确 live bridge 才是 eventual close owner
- `tests/Integration/test_child_thread_live_bridge.py`
  - 新增 integration proof：
    - child run 完成后，实例会 close + detach
    - thread detail/runtime 仍可通过 persisted truth + lazy rebuild 继续读取

@@@web-child-run-complete-owner - child thread 可见性继续由 persisted thread/task surface 承担，不再通过把 finished child LeonAgent 实例钉在 agent_pool 里来获得。

### Slice B: cleanup signal ownership

第二刀收的是更底层的 ownership 重建：

- `core/runtime/cleanup.py`
  - `CleanupRegistry` 不再注册 process signal handler
  - 它只保留 cleanup function registry / priority runner 语义
- `tests/Unit/core/test_runtime_support.py`
  - 改成证明 `CleanupRegistry` 默认不抢 signal owner

@@@cleanup-signal-owner - process signal belongs to app/CLI graceful-shutdown owner, not to every LeonAgent-local cleanup helper.

## Evidence

### 真实产品验证

- fresh caller-proven backend proof 已重新拿到
- patched backend `:18047`
- login / create thread / subagent success path caller-proven 为绿：
  - `tool_call Agent`
  - `tool_result Agent -> SUBAGENT_CLOSE_OWNERSHIP_1775800001`
  - `final assistant -> SUBAGENT_CLOSE_OWNERSHIP_1775800001`
- Slice A 之后的 fresh falsification 也已记录：
  - 对 uvicorn pid `47839` 发送 `SIGTERM` 后，连续 10 秒仍然：
    - process alive
    - `GET /openapi.json -> 200`
  - 这把 root cause 继续压到了 per-agent signal ownership
- Slice B 后的 fresh caller-proof：
  - patched backend `:18047`
  - fresh subagent thread:
    - `m_dKjuBBLbR1bw-84`
  - exact token:
    - `SUBAGENT_CLOSE_OWNERSHIP_1775800201`
  - caller-proven sequence:
    1. `/api/auth/login -> 200`
    2. `/api/threads -> 200`
    3. `/api/threads/{thread_id}/messages -> 200`
    4. `history` shows:
       - `tool_call Agent`
       - `tool_result Agent -> SUBAGENT_CLOSE_OWNERSHIP_1775800201`
       - `final assistant -> SUBAGENT_CLOSE_OWNERSHIP_1775800201`
    5. `SIGTERM` sent to uvicorn pid `53201`
    6. poll result:
       - `poll 0`: `alive=True`, `openapi=200`
       - `poll 1`: `alive=False`, `openapi=502`
       - later polls remain dead
    7. shutdown log:
       - `Shutting down`
       - `Waiting for application shutdown.`
       - `Application shutdown complete.`
       - `Finished server process [53201]`

### 机制层验证

- `Claude Code / cc-src` 核查结论：
  - retained truth = task / transcript / metadata
  - resume = transcript + metadata 驱动的新 lifecycle
  - 不是 resident completed instance

### 源码/测试层辅助证据

- `uv run pytest -q tests/Integration/test_child_thread_live_bridge.py`
  - `19 passed in 0.38s`
- `uv run pytest -q tests/Integration/test_query_loop_backend_bridge.py -k 'subagent or child_thread or Agent'`
  - `18 passed, 19 deselected in 1.12s`
- combined:
  - `uv run pytest -q tests/Integration/test_child_thread_live_bridge.py tests/Integration/test_query_loop_backend_bridge.py`
  - `56 passed in 0.47s`
- `uv run pytest -q tests/Unit/core/test_runtime_support.py -k 'cleanup_registry_does_not_install_process_signal_handlers or cleanup_registry_runs_in_priority_order_and_survives_failures or cleanup_registry_reuses_first_inflight_run or cleanup_registry_register_returns_deregister_handle'`
  - `4 passed, 9 deselected in 0.01s`
- updated integration pack after Slice B:
  - `uv run pytest -q tests/Integration/test_child_thread_live_bridge.py tests/Integration/test_query_loop_backend_bridge.py -k 'subagent or child_thread or Agent'`
  - `37 passed, 19 deselected in 0.47s`
- `uv run ruff check backend/web/services/streaming_service.py core/agents/service.py tests/Integration/test_child_thread_live_bridge.py`
  - `All checks passed!`
- `uv run ruff check core/runtime/cleanup.py tests/Unit/core/test_runtime_support.py`
  - `All checks passed!`
- `uv run python -m py_compile backend/web/services/streaming_service.py core/agents/service.py tests/Integration/test_child_thread_live_bridge.py`
  - `exit 0`
- `uv run python -m py_compile core/runtime/cleanup.py tests/Unit/core/test_runtime_support.py`
  - `exit 0`

## Stopline

- 不把“child 可复用”错误实现成“child instance 常驻直到进程退出”
- 不顺手扩成更大的 main/subagent architecture rewrite
- 不混入 remote provider 语义
- 不为了证明这刀而捏造 fake backend proof

当前这四条都已满足。

## Closure ruling

- 这张卡的实现、真实产品验证、机制层验证、源码/测试层辅助证据已经齐备
- `ready_for_review` 现在只是 stale 状态，不再代表真实 stopline
- 这张卡到这里可以 closure
