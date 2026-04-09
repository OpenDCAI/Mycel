---
title: Current State Inventory
status: done
created: 2026-04-09
---

# Current State Inventory

目标：给 `origin/dev = f0264bfdd1d204f1b0b24c924451c2097788e0c3` 做一次诚实 inventory，避免后续继续按 2026-04-09 的旧 worktree 结论推进。

## 当前结论

### 已经对齐到 strategy/container seam 的部分

- [backend/web/core/lifespan.py](backend/web/core/lifespan.py)
- [backend/web/services/file_channel_service.py](backend/web/services/file_channel_service.py)
- [backend/web/services/monitor_service.py](backend/web/services/monitor_service.py)
- [backend/web/utils/helpers.py](backend/web/utils/helpers.py)
- [backend/web/routers/webhooks.py](backend/web/routers/webhooks.py)
- [backend/web/routers/threads.py](backend/web/routers/threads.py)
- [sandbox/control_plane_repos.py](sandbox/control_plane_repos.py)
- [storage/runtime.py](storage/runtime.py)

### 仍然保留 SQLite 的部分，但并不都算 blocker

- [core/runtime/middleware/queue/manager.py](core/runtime/middleware/queue/manager.py)
- [core/runtime/middleware/memory/summary_store.py](core/runtime/middleware/memory/summary_store.py)
- [storage/session_manager.py](storage/session_manager.py)
- [sandbox/runtime.py](sandbox/runtime.py)
- [sandbox/capability.py](sandbox/capability.py)
- [sandbox/terminal.py](sandbox/terminal.py)

这些路径里有一部分是“显式本地 `db_path` 合同保留”，不应再被误记成同级 residual。

### 当前最值钱的真实 residual

- sandbox control-plane 在 strategy path 下仍有 contract gap
- fresh audit 直接打出来的是：
  - [sandbox/manager.py](sandbox/manager.py) 依赖 `lease_store.set_volume_id(...)`
  - `dev` 上的 [storage/providers/supabase/lease_repo.py](storage/providers/supabase/lease_repo.py) 尚未实现这条合同

## Inventory ruling

- 早期“service surface / control-plane / side-store / default cut”这套分层仍然有效
- 但 current `dev` 上真正优先级最高的 residual 已经不是 broad service surface
- 当前应该把注意力集中到：
  1. sandbox control-plane contract gap
  2. closure proof 质量
  3. default/env-less contract 的诚实边界
