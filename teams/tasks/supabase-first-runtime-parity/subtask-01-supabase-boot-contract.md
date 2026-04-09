---
title: Supabase Boot Contract
status: in_progress
created: 2026-04-09
---

# Supabase Boot Contract

目标：定义并验证 `LEON_STORAGE_STRATEGY=supabase` 下系统独立启动所需的最小 contract，不再把 SQLite 当成隐含前提。

## 第一轮事实

### 已经存在的 Supabase-first 启动骨架

- [backend/web/core/lifespan.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/backend/web/core/lifespan.py)
  - 启动前先强制检查：
    - `LEON_POSTGRES_URL`
  - 再直接创建：
    - `create_supabase_client()`
    - `create_public_supabase_client()`
  - 然后用 [storage/container.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/storage/container.py) 把 repo 注入到 `app.state`
- [backend/web/core/supabase_factory.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/backend/web/core/supabase_factory.py)
  - 当前明确要求：
    - `SUPABASE_INTERNAL_URL` 或 `SUPABASE_PUBLIC_URL`
    - `LEON_SUPABASE_SERVICE_ROLE_KEY`
    - `SUPABASE_ANON_KEY`
    - `SUPABASE_AUTH_URL`（可选，未给则回退到 Supabase URL）
- [storage/container.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/storage/container.py)
  - 当前已经是 `Supabase-only` composition root
  - 不再做 sqlite/supabase 二选一

### 当前 boot contract 仍未完全闭环的原因

- 虽然 web composition root 已是 Supabase-first，但系统里仍有一批 side-store / control-plane caller 会把运行面重新拖回 SQLite：
  - [storage/session_manager.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/storage/session_manager.py)
  - [core/runtime/middleware/queue/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/core/runtime/middleware/queue/manager.py)
  - [core/runtime/middleware/memory/summary_store.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/core/runtime/middleware/memory/summary_store.py)
  - [sandbox/chat_session.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/chat_session.py)
  - [sandbox/lease.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/lease.py)
  - [sandbox/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/manager.py)

### 当前 ruling

- `Supabase Boot Contract` 不是“设计上应该用 Supabase”这种泛话
- 它必须最后落成 caller-proven truth：
  - 在 `LEON_STORAGE_STRATEGY=supabase` 下，系统能独立 bringup
  - 若失败，要明确失败属于：
    - code/contract
    - auth/bootstrap
    - postgres/checkpointer
    - provider/runtime
- 在这之前，不应该把任何 SQLite stopgap 误写成“启动本来就该依赖 SQLite”

## Stopline

- 明确启动所需 env / repo / runtime 前提
- caller-proven 区分：
  - code/contract blocker
  - auth/bootstrap blocker
  - postgres/checkpointer blocker
  - provider/runtime blocker
