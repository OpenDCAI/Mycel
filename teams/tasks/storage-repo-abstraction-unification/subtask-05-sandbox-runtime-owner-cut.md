---
title: Sandbox Runtime Owner Cut
status: in_progress
created: 2026-04-09
---

# Sandbox Runtime Owner Cut

## 当前 ruling

这张卡已经进入实现期，但当前仍然不直接碰 `sandbox/manager.py`。

当前已完成的 slice 有两刀：

- [backend/web/routers/webhooks.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/backend/web/routers/webhooks.py)
- [sandbox/lease.py](/Users/lexicalmathical/worktrees/leonai--storage-lease-owner-cut/sandbox/lease.py)

因为这两刀都满足：

- runtime-owned 语义明显
- write set 足够窄
- 不会把 `sandbox/manager.py` / `helpers.py` / `threads.py` 一起卷进来

## 已完成事实

- `webhooks.py` 不再 import `SQLiteLeaseRepo`
- `webhooks.py` 改走 `storage.runtime.build_lease_repo(...)`
- unmatched webhook 的 outward payload shape 保持不变
- `sandbox/lease.py` 不再 import `backend.web.core.storage_factory`
- `sandbox/lease.py:_make_lease_repo()` 改走 `storage.runtime.build_lease_repo(...)`
- `_make_lease_repo(db_path=None)` 的 monkeypatch surface 继续保留，没有顺手改 lease contract

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

## 还没做

`CP05` 还没有 closure。剩余更深的 runtime-owned 残留仍在：

- [sandbox/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/sandbox/manager.py)
- [backend/web/utils/helpers.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/backend/web/utils/helpers.py)
- [backend/web/routers/threads.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/backend/web/routers/threads.py)

## Stopline

- 当前不直接碰 `sandbox/manager.py`
- 当前不把 `helpers.py / threads.py` 混进 `sandbox/lease.py` 同一刀
- 当前不把 `sandbox/manager.py` 和更深的 runtime lifecycle 重写混进同一刀
