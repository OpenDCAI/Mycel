---
title: Service Surface Parity
status: done
created: 2026-04-09
---

# Service Surface Parity

目标：收 web/service 层仍然 SQLite-only 的路径，让 service surface 在 `LEON_STORAGE_STRATEGY=supabase` 下不再隐含依赖 SQLite。

## Current Slice

- `backend/web/services/file_channel_service.py`
  - 不再直接 import `SQLiteLeaseRepo` / `SQLiteTerminalRepo`
  - 改为通过 `storage.runtime.build_lease_repo(...)` / `build_terminal_repo(...)` 取 repo
  - `_resolve_volume_source(...)` 的 lease -> terminal -> sandbox volume 逻辑保持不变

## Evidence

- `机制层验证`
  - `uv run pytest -q tests/Integration/test_thread_files_channel_shell.py`
    - `7 passed`
- `源码/测试层辅助证据`
  - `uv run ruff check backend/web/services/file_channel_service.py tests/Integration/test_thread_files_channel_shell.py`
    - `All checks passed!`
  - `uv run python -m py_compile backend/web/services/file_channel_service.py tests/Integration/test_thread_files_channel_shell.py`
    - `exit 0`

## Remaining

- 当前 `backend/web/services` 里的剩余 SQLite residual 只剩：
  - `monitor_service.py`
  - `sandbox_service.py`
- 两者都已不再是单纯的 service repo construction seam，而更接近 sandbox/monitor control-plane owner
- 所以下一阶段应转入 `CP03 Sandbox Control Plane Parity`

## Stopline

- service layer 不再通过 SQLite stopgap 维持运行
- 变更按小簇切，不把 sandbox/control-plane 混进同一刀
