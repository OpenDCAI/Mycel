---
title: Web Thread/File Helper Cut
status: in_progress
created: 2026-04-09
---

# Web Thread/File Helper Cut

## 当前 ruling

这张卡现在已经拆成两层：

- `CP04a file/helper slice`
  - [backend/web/services/activity_tracker.py](/Users/lexicalmathical/worktrees/leonai--storage-file-helper-cut/backend/web/services/activity_tracker.py)
  - [backend/web/services/file_channel_service.py](/Users/lexicalmathical/worktrees/leonai--storage-file-helper-cut/backend/web/services/file_channel_service.py)
- 剩余 residual
  - `backend/web/utils/helpers.py`
  - `backend/web/routers/threads.py`
  - `backend/web/routers/webhooks.py`

## 已完成事实

`CP04a` 已落地：

- `activity_tracker.py` 不再 import `backend.web.core.storage_factory`
- `file_channel_service.py` 不再 import `backend.web.core.storage_factory`
- [storage/runtime.py](/Users/lexicalmathical/worktrees/leonai--storage-file-helper-cut/storage/runtime.py) 新增 `build_terminal_repo(...)`
- module-local `make_chat_session_repo / make_lease_repo / make_terminal_repo` 名字仍保留

## 证据

- red:
  - `uv run pytest -q tests/Integration/test_thread_files_channel_shell.py -k 'file_channel_and_activity_tracker_no_longer_import_storage_factory'`
  - `1 failed, 5 deselected`
- green:
  - `uv run pytest -q tests/Integration/test_thread_files_channel_shell.py`
  - `6 passed`
  - `uv run ruff check storage/runtime.py backend/web/services/activity_tracker.py backend/web/services/file_channel_service.py tests/Integration/test_thread_files_channel_shell.py`
  - `All checks passed!`
  - `uv run python -m py_compile storage/runtime.py backend/web/services/activity_tracker.py backend/web/services/file_channel_service.py tests/Integration/test_thread_files_channel_shell.py`
  - `exit 0`

## 还没做

这张卡还没有 closure。剩余更像下一刀的是：

- `helpers.py` 的 runtime/db-path helper seam
- `threads.py` / `webhooks.py` 的 lease/terminal helper seam

## Stopline

- 当前不碰 `backend/web/utils/helpers.py`
- 当前不碰 `backend/web/routers/threads.py`
- 当前不碰 `backend/web/routers/webhooks.py`
