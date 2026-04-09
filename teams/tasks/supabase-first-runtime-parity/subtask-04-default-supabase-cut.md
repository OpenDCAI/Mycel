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
- 当前代码里最硬的 default fallback 只剩两处：
  - `backend/web/services/monitor_service.py`
  - `sandbox/lease.py`
- 所以第一轮实现只收这两个 fallback：
  - `runtime_health_snapshot()` 不再把缺省 strategy 当成 sqlite
  - `_use_supabase_storage()` 不再把缺省 strategy 当成 sqlite

## First Slice

- `backend/web/services/monitor_service.py`
  - `os.getenv("LEON_STORAGE_STRATEGY") or "supabase"`
- `sandbox/lease.py`
  - `os.getenv("LEON_STORAGE_STRATEGY", "supabase")`
- 这刀不碰：
  - `monitor_service.py` 更深的 sqlite diagnostics seam
  - `sandbox/lease.py` 更深的 sqlite local persistence helpers
  - `CP05 closure proof`

## Evidence

- `机制层验证`
  - `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py tests/Unit/sandbox/test_lease_probe_contract.py -k 'defaults_to_supabase_when_strategy_missing or use_supabase_storage_defaults_true_when_strategy_missing or runtime_health_snapshot_reports_supabase_storage_contract'`
    - `3 passed, 27 deselected`
  - `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py`
    - `16 passed`
  - `uv run pytest -q tests/Unit/sandbox/test_lease_probe_contract.py`
    - `14 passed`
- `源码/测试层辅助证据`
  - `uv run ruff check backend/web/services/monitor_service.py sandbox/lease.py tests/Unit/monitor/test_monitor_compat.py tests/Unit/sandbox/test_lease_probe_contract.py`
    - `All checks passed!`
  - `uv run python -m py_compile backend/web/services/monitor_service.py sandbox/lease.py tests/Unit/monitor/test_monitor_compat.py tests/Unit/sandbox/test_lease_probe_contract.py`
    - `exit 0`

## Current Stopline

- 这刀只说明：
  - 当前代码的缺省 strategy fallback 已改成 Supabase
- 这不等于：
  - 系统在“完全不依赖 SQLite”下已经 closure
  - boot/runtime proof 已完成
- 下一步如果继续，应转向：
  - 补 `CP04` 更高层的 default/dev contract proof
  - 或直接进入 `CP05 Closure Proof`

## Stopline

- 默认 bringup/documented contract 明确是 Supabase
- SQLite 仍可作为一种 strategy，但不是默认路径
