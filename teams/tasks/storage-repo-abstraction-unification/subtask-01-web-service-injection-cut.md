---
title: Web Service Injection Cut
status: done
created: 2026-04-09
---

# Web Service Injection Cut

## 已完成事实

- `task_service.py` 与 `cron_job_service.py` 默认 repo path 已不再 import `backend.web.core.storage_factory`
- 默认 path 改走 `storage.runtime`
- 没有顺手扩大到 monitor/resource

## 证据

- `uv run pytest -q tests/Integration/test_panel_task_owner_contract.py`
  - `9 passed`
- `uv run ruff check storage/runtime.py backend/web/services/task_service.py backend/web/services/cron_job_service.py tests/Integration/test_panel_task_owner_contract.py`
  - `All checks passed!`

