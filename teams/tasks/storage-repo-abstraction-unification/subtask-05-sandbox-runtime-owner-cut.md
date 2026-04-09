---
title: Sandbox Runtime Owner Cut
status: in_progress
created: 2026-04-09
---

# Sandbox Runtime Owner Cut

## 当前 ruling

这张卡仍在实现期。目前已完成四刀：

- [backend/web/routers/webhooks.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/backend/web/routers/webhooks.py)
- [sandbox/lease.py](/Users/lexicalmathical/worktrees/leonai--storage-lease-owner-cut/sandbox/lease.py)
- [sandbox/resource_snapshot.py](/Users/lexicalmathical/worktrees/leonai--storage-lease-owner-cut/sandbox/resource_snapshot.py)
- [backend/web/routers/threads.py](/Users/lexicalmathical/worktrees/leonai--storage-thread-sandbox-cut/backend/web/routers/threads.py)
- [sandbox/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-sandbox-manager-cut/sandbox/manager.py)

<<<<<<< HEAD
因为这几刀都满足：

- runtime-owned 语义明显
- write set 足够窄
- 不会把 `sandbox/manager.py` / `helpers.py` / `threads.py` 一起卷进来

## 已完成事实

- `webhooks.py` 不再 import `SQLiteLeaseRepo`
- `webhooks.py` 改走 `storage.runtime.build_lease_repo(...)`
- unmatched webhook 的 outward payload shape 保持不变
- `sandbox/lease.py` 不再 import `backend.web.core.storage_factory`
- `sandbox/lease.py:_make_lease_repo()` 保持 runtime-owned sqlite constructor
- `_make_lease_repo(db_path=None)` 的 monkeypatch surface 继续保留，没有顺手改 lease contract
- `sandbox/resource_snapshot.py` 不再让 snapshot write failure 反向变成 local runtime bringup contract
- `threads.py:_create_thread_sandbox_resources()` 不再 import `backend.web.core.storage_factory`
- `threads.py` 的 lease / terminal row bootstrap 改走 `storage.runtime.build_lease_repo(...)` 与 `build_terminal_repo(...)`
- thread sandbox bootstrap 的 outward behavior 保持不变，local cwd contract 继续由现有 route test 固定
- `sandbox/manager.py` 不再 import `backend.web.core.storage_factory`
- `sandbox/manager.py` 顶层 `make_chat_session_repo / make_lease_repo / make_terminal_repo` 全部改走 `storage.runtime`
- 既有 monkeypatch 面继续保留，所以 manager strategy tests 不需要改调用协议

## 证据

- `CP05a`
  - red:
    - `uv run pytest -q tests/Integration/test_webhooks_router_contract.py`
    - `2 failed`
  - green:
    - `uv run pytest -q tests/Integration/test_webhooks_router_contract.py`
    - `2 passed`
    - `uv run ruff check backend/web/routers/webhooks.py tests/Integration/test_webhooks_router_contract.py`
    - `All checks passed!`
    - `uv run python -m py_compile backend/web/routers/webhooks.py tests/Integration/test_webhooks_router_contract.py`
    - `exit 0`
- `CP05b`
  - red:
    - `uv run pytest -q tests/Unit/sandbox/test_lease_probe_contract.py -k 'sandbox_lease_no_longer_imports_storage_factory or ensure_active_instance_persists_strategy_lease_before_probe_failure'`
    - `1 failed, 1 passed`
  - green:
    - `uv run pytest -q tests/Unit/sandbox/test_lease_probe_contract.py`
    - `2 passed`
    - `uv run ruff check sandbox/lease.py tests/Unit/sandbox/test_lease_probe_contract.py`
    - `All checks passed!`
    - `uv run python -m py_compile sandbox/lease.py tests/Unit/sandbox/test_lease_probe_contract.py`
    - `exit 0`
- `CP05b follow-up`
  - red:
    - `uv run pytest -q tests/Unit/core/test_capability_async.py -k 'local_sandbox_rebuilds_stale_closed_capability_before_execute_async'`
    - `1 failed`
  - green:
    - same command
    - `1 passed`
- `CP05c`
  - red:
    - `uv run pytest -q tests/Integration/test_threads_router.py -k 'threads_router_sandbox_bootstrap_no_longer_imports_storage_factory or create_thread_route_passes_local_cwd_into_sandbox_bootstrap'`
    - `1 failed, 1 passed`
  - green:
    - `uv run pytest -q tests/Integration/test_threads_router.py -k 'threads_router_sandbox_bootstrap_no_longer_imports_storage_factory or create_thread_route_passes_local_cwd_into_sandbox_bootstrap'`
    - `2 passed, 25 deselected`
    - `uv run ruff check backend/web/routers/threads.py tests/Integration/test_threads_router.py`
    - `All checks passed!`
    - `uv run python -m py_compile backend/web/routers/threads.py tests/Integration/test_threads_router.py`
    - `exit 0`
- `CP05d`
  - red:
    - `uv run pytest -q tests/Unit/sandbox/test_manager_repo_strategy.py -k 'sandbox_manager_no_longer_imports_storage_factory or sandbox_manager_uses_strategy_aware_repos_under_supabase'`
    - `1 failed, 1 passed`
  - green:
    - `uv run pytest -q tests/Unit/sandbox/test_manager_repo_strategy.py`
    - `10 passed`
    - `uv run ruff check sandbox/manager.py tests/Unit/sandbox/test_manager_repo_strategy.py`
    - `All checks passed!`
    - `uv run python -m py_compile sandbox/manager.py tests/Unit/sandbox/test_manager_repo_strategy.py`
    - `exit 0`

## 还没做

`CP05` 还没有 closure。source scan 证明还存在一个 live production residual：

- [sandbox_service.py](/Users/lexicalmathical/worktrees/leonai--storage-sandbox-manager-cut/backend/web/services/sandbox_service.py)

## Stopline

- 当前不把 `sandbox_service.py` 混进 `sandbox/manager.py` 同一刀
- 当前不把 `CP05` 假装成已经 closure
- `CP06` 删除 `storage_factory.py` 必须等最后这个 live callsite 收掉之后再进

## Hindsight

- `db_path` holder 离开 `storage_factory`，不自动意味着应该改走 `storage.runtime`
- `sandbox/lease.py` 的 owner 是 runtime-local sqlite lease storage，不是 Supabase runtime builder
