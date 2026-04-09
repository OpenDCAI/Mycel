---
title: Sandbox Runtime Owner Cut
status: in_progress
created: 2026-04-09
---

# Sandbox Runtime Owner Cut

## 当前 ruling

这张卡已经进入实现期，但第一刀不是直接碰 `sandbox/manager.py`。

当前已完成的 `CP05a` 是：

- [backend/web/routers/webhooks.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/backend/web/routers/webhooks.py)

因为它已经满足：

- runtime-owned 语义明显
- write set 足够窄
- 不会把 `sandbox/manager.py` / `sandbox/lease.py` 一起卷进来

## 已完成事实

- `webhooks.py` 不再 import `SQLiteLeaseRepo`
- `webhooks.py` 改走 `storage.runtime.build_lease_repo(...)`
- unmatched webhook 的 outward payload shape 保持不变

## 证据

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

## 还没做

`CP05` 还没有 closure。剩余更深的 runtime-owned 残留仍在：

- [sandbox/lease.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/sandbox/lease.py)
- [sandbox/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/sandbox/manager.py)
- [backend/web/utils/helpers.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/backend/web/utils/helpers.py)
- [backend/web/routers/threads.py](/Users/lexicalmathical/worktrees/leonai--storage-webhooks-lease-cut/backend/web/routers/threads.py)

## Stopline

- 当前不直接碰 `sandbox/lease.py`
- 当前不直接碰 `sandbox/manager.py`
- 当前不把 `helpers.py / threads.py` 混进同一刀
