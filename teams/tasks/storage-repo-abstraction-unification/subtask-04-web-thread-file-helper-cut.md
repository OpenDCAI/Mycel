---
title: Web Thread/File Helper Cut
status: done
created: 2026-04-09
---

# Web Thread/File Helper Cut

## 当前 ruling

这张卡已经完成 closure，实际是两刀：

- `CP04a file/helper slice`
  - [backend/web/services/activity_tracker.py](/Users/lexicalmathical/worktrees/leonai--storage-file-helper-cut/backend/web/services/activity_tracker.py)
  - [backend/web/services/file_channel_service.py](/Users/lexicalmathical/worktrees/leonai--storage-file-helper-cut/backend/web/services/file_channel_service.py)
- `CP04b helpers slice`
  - [backend/web/utils/helpers.py](/Users/lexicalmathical/worktrees/leonai--storage-helpers-cut/backend/web/utils/helpers.py)

`threads.py / webhooks.py` 这两块已经被重分流到 `CP05`，因为它们更像 runtime-owned lease/terminal seam，而不是普通 web helper seam。

## 已完成事实

`CP04a` 已落地：

- `activity_tracker.py` 不再 import `backend.web.core.storage_factory`
- `file_channel_service.py` 不再 import `backend.web.core.storage_factory`
- `file_channel_service.py` 最终没有保留 `storage.runtime` terminal/lease builder 路径
- 因为 thread -> terminal -> lease 这条 file-channel lookup 仍然是 `sandbox.db` 的 `db_path` owner seam
- 所以 `file_channel_service.py` 现在显式持有本地 sqlite `lease/terminal` constructor，而不是误接到 Supabase-only runtime builder
- module-local `make_lease_repo / make_terminal_repo` 名字仍保留

`CP04b` 已落地：

- `helpers.py` 不再 import `backend.web.core.storage_factory`
- `helpers.py` 改走 `storage.runtime.build_chat_session_repo(...)` / `build_lease_repo(...)` / `build_terminal_repo(...)`
- `SANDBOX_DB_PATH`、timestamp helper、thread purge helper 的现有行为保持不变

## 证据

- `CP04a`
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
- `CP04b`
  - red:
    - `uv run pytest -q tests/Integration/test_thread_files_channel_shell.py -k 'helpers_no_longer_import_storage_factory or file_channel_and_activity_tracker_no_longer_import_storage_factory'`
    - `1 failed, 1 passed`
  - green:
    - `uv run pytest -q tests/Integration/test_thread_files_channel_shell.py`
    - `7 passed`
    - `uv run ruff check backend/web/utils/helpers.py tests/Integration/test_thread_files_channel_shell.py`
    - `All checks passed!`
    - `uv run python -m py_compile backend/web/utils/helpers.py tests/Integration/test_thread_files_channel_shell.py`
    - `exit 0`

## Stopline

- `CP04` 到这里已经 closure
- 已经转入 `CP05` 的 `threads.py / webhooks.py` 不再回拉
- 当前不把 `helpers.py` closure 假装成 `sandbox/manager.py` 的默认下一刀

### Hindsight

- `no longer imports storage_factory` 不等于 `应该改走 storage.runtime`
- 如果代码本身就是 `sandbox.db` / `db_path` lookup owner，最小而诚实的落点仍然可能是本地 sqlite constructor
