---
title: Current State Inventory
status: in_progress
created: 2026-04-09
---

# Current State Inventory

目标：固化 current `dev` 下所有仍依赖 SQLite、或仅在 SQLite 语义下成立的 runtime/service/control-plane 路径，避免后续“凭印象推进”。

## 关注点

- 直接 import `storage.providers.sqlite.*` 的 production path
- 依赖 `sandbox.db` / `db_path` 的 caller
- `LEON_STORAGE_STRATEGY=supabase` 下仍会退化到 SQLite 的路径
- 默认配置仍非 Supabase-first 的入口

## 第一轮 inventory 结论

### 已经对齐到 Supabase-first 的部分

- [backend/web/core/lifespan.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/backend/web/core/lifespan.py)
  - 当前 authoritative web composition root 已经直接创建 Supabase client
  - 再通过 [storage/container.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/storage/container.py) 注入：
    - `user_repo`
    - `thread_repo`
    - `lease_repo`
    - `terminal_repo`
    - `chat_session_repo`
    - `sandbox_volume_repo`
    - `panel_task_repo`
    - `cron_job_repo`
- 这说明“默认 composition root 应该是 Supabase-first”已经有真实骨架，不是从零开始

### 当前最明显的 SQLite-only 残余

#### 1. File channel / volume lookup

- [backend/web/services/file_channel_service.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/backend/web/services/file_channel_service.py)
  - 直接 import:
    - `SQLiteLeaseRepo`
    - `SQLiteTerminalRepo`
  - 通过 `SANDBOX_DB_PATH` 读取 thread -> terminal -> lease -> volume_id 链

#### 2. Sandbox control-plane

- [sandbox/chat_session.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/chat_session.py)
  - 直接 new:
    - `SQLiteChatSessionRepo`
    - `SQLiteTerminalRepo`
    - `SQLiteLeaseRepo`
- [sandbox/lease.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/lease.py)
  - `_make_lease_repo()` 直接返回 `SQLiteLeaseRepo`
- [sandbox/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/manager.py)
  - 顶层 `make_chat_session_repo / make_lease_repo / make_terminal_repo` 都直接返回 SQLite repo

#### 3. Session/checkpoint side-store

- [storage/session_manager.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/storage/session_manager.py)
  - 仍直接依赖：
    - `SQLiteCheckpointRepo`
    - `SQLiteFileOperationRepo`

#### 4. Runtime middleware side stores

- [core/runtime/middleware/queue/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/core/runtime/middleware/queue/manager.py)
  - 仍直接 new `SQLiteQueueRepo`
- [core/runtime/middleware/memory/summary_store.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/core/runtime/middleware/memory/summary_store.py)
  - 仍直接 new `SQLiteSummaryRepo`

### 当前 ruling

- `#191` 已完成的是“抽象层/旧桥 closure”
- 新 lane 的核心不是再删桥，而是把这些仍然 SQLite-only 的运行路径继续推到 provider-parity
- 第一刀不该先碰整个 sandbox 架构
- 最自然的切分是：
  1. `service surface`
  2. `control-plane`
  3. `side-store / middleware`
  4. `default Supabase boot contract`

## Stopline

- 给出按 owner/seam 分层的残余清单
- 明确哪些是 service surface，哪些是 sandbox control-plane，哪些是 boot/default contract
