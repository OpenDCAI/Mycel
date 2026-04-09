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

`threads.py / webhooks.py` 这两块已经被重分流到 `CP05`，因为它们更像 runtime-owned lease/terminal seam，而不是普通 web helper seam。

## 已完成事实

`CP04a` 已落地：

- `activity_tracker.py` 不再 import `backend.web.core.storage_factory`
- `file_channel_service.py` 不再 import `backend.web.core.storage_factory`
- `file_channel_service.py` 最终没有保留 `storage.runtime` terminal/lease builder 路径
- 因为 thread -> terminal -> lease 这条 file-channel lookup 仍然是 `sandbox.db` 的 `db_path` owner seam
- 所以 `file_channel_service.py` 现在显式持有本地 sqlite `lease/terminal` constructor，而不是误接到 Supabase-only runtime builder
- module-local `make_lease_repo / make_terminal_repo` 名字仍保留

## 证据

- red:
  - `uv run pytest -q tests/Integration/test_thread_files_channel_shell.py -k 'file_channel_and_activity_tracker_no_longer_import_storage_factory'`
  - `1 failed, 5 deselected`
- green:
  - `uv run pytest -q tests/Unit/core/test_agent_pool.py -k 'creates_once_per_thread or ignores_unavailable_local_cwd or honors_fresh_local_thread_cwd_even_when_missing or prefers_repo_backed_runtime_startup_even_with_conflicting_legacy_member_shell or uses_thread_user_id_for_chat_identity'`
  - `5 passed, 2 deselected`
  - `uv run pytest -q tests/Integration/test_thread_files_channel_shell.py`
  - `6 passed`
  - `uv run ruff check backend/web/services/file_channel_service.py tests/Integration/test_thread_files_channel_shell.py tests/Unit/core/test_agent_pool.py`
  - `All checks passed!`
  - `uv run python -m py_compile backend/web/services/file_channel_service.py tests/Integration/test_thread_files_channel_shell.py tests/Unit/core/test_agent_pool.py`
  - `exit 0`

## 还没做

这张卡还没有 closure。当前只剩一个 residual：

- `helpers.py` 的 runtime/db-path helper seam

## Stopline

- 当前不碰 `backend/web/utils/helpers.py`
- 当前不把 `helpers.py` 和 `sandbox/manager.py` 混成一刀
- 当前不把已经转入 `CP05` 的 `threads.py / webhooks.py` 再拉回这张卡

### Hindsight

- `no longer imports storage_factory` 不等于 `应该改走 storage.runtime`
- 如果代码本身就是 `sandbox.db` / `db_path` lookup owner，最小而诚实的落点仍然可能是本地 sqlite constructor
