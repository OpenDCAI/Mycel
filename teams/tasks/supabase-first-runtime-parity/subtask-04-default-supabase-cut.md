---
title: Default Supabase Cut
status: in_progress
created: 2026-04-09
---

# Default Supabase Cut

目标：把默认本地/开发主线配置收成 Supabase-first，而不是继续默认落在 SQLite 假设上。

## Current Ruling

- `CP04` 第一刀不碰更高层 boot/runtime proof。
- 这刀只回答一个更小的问题：
  - 当 `LEON_STORAGE_STRATEGY` 没有显式设置时，代码默认把系统解释成什么 strategy。
- 当前代码里最硬的 default fallback 看起来只剩两处：
  - `backend/web/services/monitor_service.py`
  - `sandbox/lease.py`
- 但第一轮实现后确认：
  - `runtime_health_snapshot()` 可以安全改成 supabase-first
  - `_use_supabase_storage()` 不能直接改成 supabase-first
  - 因为 env 缺省时，sandbox control-plane 仍会先走本地 sqlite lease truth
- 第二轮实现后又确认：
  - web startup 里的 `queue_manager` 也不能继续裸建 sqlite repo
  - generic `create_leon_agent()` 在 `LEON_STORAGE_STRATEGY=supabase` 下也必须自动接上 runtime storage container
  - 否则 queue / summary 会继续绕开 strategy，和 documented default contract 冲突

## First Slice

- `backend/web/services/monitor_service.py`
  - `os.getenv("LEON_STORAGE_STRATEGY") or "supabase"`
- `sandbox/lease.py`
  - 保持 `os.getenv("LEON_STORAGE_STRATEGY", "sqlite")`
  - 新增 regression，证明 env 缺省时 `mark_needs_refresh()` 仍必须写回本地 sqlite lease row
- 这刀不碰：
  - `monitor_service.py` 更深的 sqlite diagnostics seam
  - `sandbox/lease.py` 更深的 sqlite local persistence helpers
  - `sandbox/control_plane_repos.py` / `sandbox/manager.py` 的 env-less sqlite ownership
  - `CP05 closure proof`

## Second Slice

- `backend/web/core/lifespan.py`
  - `app.state.queue_manager` 改为 `MessageQueueManager(repo=storage_container.queue_repo())`
- `core/runtime/agent.py`
  - `create_leon_agent()` 在 `LEON_STORAGE_STRATEGY=supabase` 且未显式注入 container 时，自动 `build_storage_container()`
  - `LeonAgent` 在已有 `storage_container` 且未显式注入 `queue_manager` 时，默认走 `storage_container.queue_repo()`
- 这一刀顺带把 generic agent / `langgraph_app.py` 的 summary persistence 也拉回 runtime container
  - 因为 `LeonAgent._add_memory_middleware()` 已经优先消费 `storage_container.summary_repo()`
- 这刀仍不碰：
  - queue repo / summary repo 更深的 provider parity 实现
  - README / quickstart / deployment / configuration 文档 truth
  - env-less sandbox control-plane sqlite ownership

## Evidence

- `机制层验证`
  - `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py tests/Unit/sandbox/test_lease_probe_contract.py -k 'defaults_to_supabase_when_strategy_missing or use_supabase_storage_defaults_false_when_strategy_missing or mark_needs_refresh_without_strategy_env_uses_local_sqlite or runtime_health_snapshot_reports_supabase_storage_contract'`
    - `4 passed, 27 deselected`
  - `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py`
    - `16 passed`
  - `uv run pytest -q tests/Unit/sandbox/test_lease_probe_contract.py`
    - `15 passed`
  - `uv run pytest -q tests/Integration/test_storage_repo_abstraction_unification.py`
    - `14 passed`
  - `uv run pytest -q tests/Integration/test_leon_agent.py -k 'create_leon_agent_supabase_defaults_wire_runtime_container or leon_agent_simple_run or leon_agent_ainit_pushes_late_checkpointer_into_memory_middleware'`
    - `3 passed, 33 deselected`
- `源码/测试层辅助证据`
  - `uv run ruff check backend/web/services/monitor_service.py sandbox/lease.py backend/web/core/lifespan.py core/runtime/agent.py tests/Unit/monitor/test_monitor_compat.py tests/Unit/sandbox/test_lease_probe_contract.py tests/Integration/test_storage_repo_abstraction_unification.py tests/Integration/test_leon_agent.py`
    - `All checks passed!`
  - `uv run python -m py_compile backend/web/services/monitor_service.py sandbox/lease.py backend/web/core/lifespan.py core/runtime/agent.py tests/Unit/monitor/test_monitor_compat.py tests/Unit/sandbox/test_lease_probe_contract.py tests/Integration/test_storage_repo_abstraction_unification.py tests/Integration/test_leon_agent.py`
    - `exit 0`

## Current Stopline

- 这刀只说明：
  - web-facing monitor read surface 的缺省 strategy fallback 已改成 Supabase
  - `sandbox/lease.py` 的缺省 strategy fallback 还不能改
  - 否则会把 env-less sqlite control-plane 和 strategy lease repo 撕成 split-brain
  - web startup queue 和 generic agent startup queue/summary 已经接回 runtime storage container
- 这不等于：
  - 系统在“完全不依赖 SQLite”下已经 closure
  - boot/runtime proof 已完成
- 下一步如果继续，应转向：
  - 补 `CP04` 更高层的 default/dev contract proof
  - 盘清 README / quickstart / deployment / configuration 的 documented truth
  - 再决定 `CP05 Closure Proof` 的真实入口

## Stopline

- documented/default bringup contract 明确是 Supabase-first
- 不再把 env-less sqlite residual 假装成“默认已经切完”
