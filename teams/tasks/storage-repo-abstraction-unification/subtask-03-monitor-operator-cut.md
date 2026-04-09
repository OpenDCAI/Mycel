---
title: Monitor Operator Cut
status: done
created: 2026-04-09
---

# Monitor Operator Cut

## 实际边界

这刀只收：

- [backend/web/services/monitor_service.py](/Users/lexicalmathical/worktrees/leonai--storage-monitor-operator-cut/backend/web/services/monitor_service.py)
- [storage/runtime.py](/Users/lexicalmathical/worktrees/leonai--storage-monitor-operator-cut/storage/runtime.py)

目标只有一个：不再让 operator monitor 一边走 Supabase monitor repo，一边再从 SQLite-only lease/chat_session repo 取 truth。

## 已完成事实

- `monitor_service.py` 不再 import `backend.web.core.storage_factory`
- `monitor_service.py` 不再 hard-import SQLite-only `LeaseRepo` / `ChatSessionRepo`
- `storage.runtime` 新增最小 builder：
  - `build_lease_repo(...)`
  - `build_chat_session_repo(...)`
- `make_sandbox_monitor_repo / make_lease_repo / make_chat_session_repo` 这组 module-local monkeypatch 名字仍保留

## 证据

- red:
  - `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'monitor_service_no_longer_imports_storage_factory_or_sqlite_repos'`
  - `1 failed, 14 deselected`
- green:
  - `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py`
  - `15 passed`
  - `uv run pytest -q tests/Integration/test_monitor_resources_route.py`
  - `15 passed`
  - `uv run ruff check storage/runtime.py backend/web/services/monitor_service.py tests/Unit/monitor/test_monitor_compat.py`
  - `All checks passed!`
  - `uv run python -m py_compile storage/runtime.py backend/web/services/monitor_service.py tests/Unit/monitor/test_monitor_compat.py`
  - `exit 0`

## Stopline

- 不碰 `resource_service.py`
- 不碰 thread/file/webhook helper
- 不删 `storage_factory.py`
