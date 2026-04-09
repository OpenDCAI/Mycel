---
title: Closure Proof
status: in_progress
created: 2026-04-09
---

# Closure Proof

目标：用真实证据证明系统在 Supabase 下可独立运行，SQLite 不再是关键路径的隐含前提。

## Current Ruling

- `CP05` 不能一上来假装完成真实产品 boot proof。
- 第一刀只回答一个更小但更硬的问题：
  - 当 `LEON_STORAGE_STRATEGY=supabase` 明确开启时，sandbox control-plane 默认 `sandbox.db` 路径是否仍然偷偷把 repo 构造绑回 SQLite。
- 当前代码在 `sandbox/control_plane_repos.py` 里仍然直接 new：
  - `SQLiteChatSessionRepo`
  - `SQLiteLeaseRepo`
  - `SQLiteTerminalRepo`
- 而 `SandboxManager(provider=p)` 会把默认 `sandbox.db` 路径显式传进这组 helper。
- 所以如果这里不先收口，后面任何 “Supabase can run independently” 的 closure 说法都不诚实。

## First Slice

- `sandbox/control_plane_repos.py`
  - 新增最小 ruling：
    - 只有在 `LEON_STORAGE_STRATEGY=supabase` 且目标路径就是默认 `sandbox.db` 时，才走：
      - `storage.runtime.build_chat_session_repo()`
      - `storage.runtime.build_lease_repo()`
      - `storage.runtime.build_terminal_repo()`
    - 显式自定义 `db_path` 仍保持 sqlite-owned
- `tests/Unit/sandbox/test_manager_repo_strategy.py`
  - 新增/翻转两条 caller-proven contract：
    - `SandboxManager(provider=...)` 在显式 Supabase + 默认 sandbox path 下，会用 strategy control-plane repos
    - `SandboxManager(provider=..., db_path=custom)` 在显式 Supabase 下仍保持本地 sqlite repo

## Second Slice

- `storage/session_manager.py`
  - `delete_thread()` 在显式 `LEON_STORAGE_STRATEGY=supabase` 下不再要求本地 `leon.db` 存在
  - 现在会通过 `storage.runtime.build_storage_container()` 取得：
    - `checkpoint_repo()`
    - `file_operation_repo()`
- `tests/Unit/storage/test_session_file_operations_cleanup.py`
  - 新增 caller-proof：
    - 显式 Supabase 下 thread cleanup 走 runtime container
    - env-less / sqlite 路径仍保持原有本地行为

## 证据要求

- 真实产品验证
- 机制层验证
- 源码/测试层辅助证据

## Evidence

- `机制层验证`
  - `uv run pytest -q tests/Unit/sandbox/test_manager_repo_strategy.py tests/Unit/sandbox/test_sandbox_manager_volume_repo.py`
    - `29 passed`
  - `uv run pytest -q tests/Unit/sandbox/test_manager_repo_strategy.py -k 'sandbox_manager_keeps_default_sandbox_repos_sqlite_owned_when_strategy_missing or sandbox_manager_uses_strategy_control_plane_repos_for_default_sandbox_db_under_supabase or sandbox_manager_keeps_custom_db_path_sqlite_owned_under_supabase'`
    - `3 passed, 10 deselected`
  - `uv run pytest -q tests/Unit/storage/test_session_file_operations_cleanup.py`
    - `2 passed`
  - `uv run pytest -q tests/Unit/sandbox/test_sandbox_manager_volume_repo.py`
    - 已包含在上一条 focused batch 中
- `源码/测试层辅助证据`
  - `uv run ruff check sandbox/control_plane_repos.py tests/Unit/sandbox/test_manager_repo_strategy.py`
    - `All checks passed!`
  - `uv run python -m py_compile sandbox/control_plane_repos.py tests/Unit/sandbox/test_manager_repo_strategy.py`
    - `exit 0`
  - `uv run ruff check storage/session_manager.py tests/Unit/storage/test_session_file_operations_cleanup.py`
    - pending fresh run for this slice
  - `uv run python -m py_compile storage/session_manager.py tests/Unit/storage/test_session_file_operations_cleanup.py`
    - pending fresh run for this slice
  - `git diff --check`
    - `exit 0`

## Current Stopline

- 这刀只说明：
  - 显式 `LEON_STORAGE_STRATEGY=supabase` 下，默认 sandbox control-plane repo construction 已回到 strategy seam
  - 显式自定义 `db_path` 仍然保留本地 sqlite 语义
  - env-less 时，默认 sandbox control-plane caller 仍然会走本地 sqlite repo truth
  - 显式 Supabase 下，`SessionManager.delete_thread()` 已不再被本地 `leon.db` existence gate 卡住
- 这不等于：
  - env-less sandbox control-plane 已经切完
  - queue / summary / other residual 已完成 closure
  - 真实产品级 Supabase boot proof 已完成

## Default Next Move

- 继续 `CP05`
  - 不扩成新的 provider parity 大刀
  - 先核对 env-less sandbox control-plane residual
  - 以及任何仍要求本地 sqlite truth 才能跑通的 default boot blocker

## Stopline

- 不用“理论上可切换”代替 caller-proven truth
