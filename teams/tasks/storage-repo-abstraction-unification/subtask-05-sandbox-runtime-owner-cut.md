---
title: Sandbox Runtime Owner Cut
status: done
created: 2026-04-09
---

# Sandbox Runtime Owner Cut

## 当前 ruling

这张卡已经 closure，但它的含义要收窄：

- 这几刀的目标是把相关 callsite 从 `storage_factory.py` 迁走，支持 `#191` 的删桥闭环
- 它们不是对 sandbox/control-plane 最终 storage 架构的终局裁决
- 尤其不应该被表述成“这些路径从此永久属于 sqlite-only owner”

最终是五刀：

- [backend/web/routers/webhooks.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/backend/web/routers/webhooks.py)
- [sandbox/lease.py](/Users/lexicalmathical/worktrees/leonai--storage-lease-owner-cut/sandbox/lease.py)
- [sandbox/resource_snapshot.py](/Users/lexicalmathical/worktrees/leonai--storage-lease-owner-cut/sandbox/resource_snapshot.py)
- [backend/web/routers/threads.py](/Users/lexicalmathical/worktrees/leonai--storage-thread-sandbox-cut/backend/web/routers/threads.py)
- [sandbox/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-sandbox-manager-cut/sandbox/manager.py)
- [backend/web/services/sandbox_service.py](/Users/lexicalmathical/worktrees/leonai--storage-sandbox-service-cut/backend/web/services/sandbox_service.py)
 
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
- `sandbox/lease.py` 在本轮里没有被粗暴塞进当前 `storage.runtime` builder，实现目标只是删桥并避免错误 owner
- `_make_lease_repo(db_path=None)` 的 monkeypatch surface 继续保留，没有顺手改 lease contract
- `sandbox/resource_snapshot.py` 不再让 snapshot write failure 反向变成 local runtime bringup contract
- `threads.py:_create_thread_sandbox_resources()` 不再 import `backend.web.core.storage_factory`
- `threads.py` 的 lease / terminal row bootstrap 改走 `storage.runtime.build_lease_repo(...)` 与 `build_terminal_repo(...)`
- thread sandbox bootstrap 的 outward behavior 保持不变，local cwd contract 继续由现有 route test 固定
- `sandbox/manager.py` 不再 import `backend.web.core.storage_factory`
- `sandbox/manager.py` 顶层 `make_chat_session_repo / make_lease_repo / make_terminal_repo` 保持 sqlite-owned constructor
- `sandbox/manager.py` 在本轮里同样只是退出 `storage_factory` 临时桥，没有在这张卡里宣称完成最终 strategy/container 化
- 既有 monkeypatch 面继续保留，所以 manager strategy tests 不需要改调用协议
- `sandbox_service.py` 不再 import `backend.web.core.storage_factory`
- `sandbox_service.py` 的 monitor repo builder 改走 `storage.runtime.build_sandbox_monitor_repo(...)`
- user-facing lease list behavior 不变，现有 `sandbox_user_leases` 与 provider availability 测试继续成立

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
    - `uv run pytest -q tests/Unit/sandbox/test_manager_repo_strategy.py -k 'sandbox_manager_no_longer_imports_storage_factory or sandbox_manager_keeps_sandbox_repos_sqlite_owned_under_supabase'`
    - `1 failed, 1 passed`
  - green:
    - `uv run pytest -q tests/Unit/sandbox/test_manager_repo_strategy.py`
    - `10 passed`
    - `uv run ruff check sandbox/manager.py tests/Unit/sandbox/test_manager_repo_strategy.py`
    - `All checks passed!`
    - `uv run python -m py_compile sandbox/manager.py tests/Unit/sandbox/test_manager_repo_strategy.py`
    - `exit 0`
- `CP05e`
  - red:
    - `uv run pytest -q tests/Unit/sandbox/test_sandbox_user_leases.py -k 'sandbox_service_no_longer_imports_storage_factory or list_user_leases_hides_subagent_threads_and_deduplicates_visible_agents'`
    - `1 failed, 1 passed`
  - green:
    - `uv run pytest -q tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py`
    - `8 passed`
    - `uv run ruff check backend/web/services/sandbox_service.py tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py`
    - `All checks passed!`
    - `uv run python -m py_compile backend/web/services/sandbox_service.py tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py`
    - `exit 0`

## Stopline

- `CP05` 到这里已经 closure
- 下一步进入 `CP06`，处理 `storage_factory.py` 删除和 closure proof

## Hindsight

- `db_path` holder 离开 `storage_factory`，不自动意味着应该改走 `storage.runtime`
- 这条经验只说明“当前 `storage.runtime` seam 不能被粗暴套到 sandbox/control-plane caller 上”，不等于这些路径的最终架构永远停在 sqlite constructor
- 如果产品目标是让整个系统在 `LEON_STORAGE_STRATEGY=supabase` 下独立运行，那么 sandbox/control-plane 的 provider-parity 需要单独 lane，而不是在 `#191` 里偷换成 stopgap closure
