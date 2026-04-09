---
title: Resource Surfaces Cut
status: done
created: 2026-04-09
---

# Resource Surfaces Cut

## 实际边界

这刀只收两处：

- [backend/web/services/resource_service.py](/Users/lexicalmathical/worktrees/leonai--storage-resource-surfaces-cut/backend/web/services/resource_service.py)
- [backend/web/services/resource_projection_service.py](/Users/lexicalmathical/worktrees/leonai--storage-resource-surfaces-cut/backend/web/services/resource_projection_service.py)

同时在 [storage/runtime.py](/Users/lexicalmathical/worktrees/leonai--storage-resource-surfaces-cut/storage/runtime.py) 增加最小 runtime seam：

- `build_sandbox_monitor_repo(...)`
- `list_resource_snapshots(...)`

`sandbox_service.py`、`resource_cache.py`、`monitor_service.py` 都不在这刀里。

## 已完成事实

- `resource_service.py` 不再 import `backend.web.core.storage_factory`
- `resource_projection_service.py` 不再 import `backend.web.core.storage_factory`
- 两个模块继续保留 `make_sandbox_monitor_repo` / `list_resource_snapshots` 这组 module-local 名字，所以现有 monkeypatch contract 没被打断
- resource/product 与 monitor/operator 两条面仍然保持分离

## 证据

- red:
  - `uv run pytest -q tests/Integration/test_resource_overview_contract_split.py -k 'resource_services_no_longer_import_storage_factory'`
  - `1 failed, 7 deselected`
- green:
  - `uv run pytest -q tests/Integration/test_resource_overview_contract_split.py tests/Integration/test_monitor_resources_route.py`
  - `23 passed`
  - `uv run pytest -q tests/Unit/backend/web/services/test_resource_projection_service_contract.py`
  - `6 passed`
  - `uv run ruff check storage/runtime.py backend/web/services/resource_service.py backend/web/services/resource_projection_service.py tests/Integration/test_resource_overview_contract_split.py tests/Unit/backend/web/services/test_resource_projection_service_contract.py`
  - `All checks passed!`
  - `uv run python -m py_compile storage/runtime.py backend/web/services/resource_service.py backend/web/services/resource_projection_service.py tests/Integration/test_resource_overview_contract_split.py tests/Unit/backend/web/services/test_resource_projection_service_contract.py`
  - `exit 0`

## Stopline

- 不碰 `monitor_service.py`
- 不碰 `sandbox_service.py`
- 不碰 thread/file helper

