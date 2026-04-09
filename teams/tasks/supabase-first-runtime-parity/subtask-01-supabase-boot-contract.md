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

## 第一轮 caller-proven 证据

### 真实产品验证

- authoritative base:
  - `origin/dev = 48e44b22aea32570749c9715b20e9b78e4c72d60`
- local tunnel truth:
  - `127.0.0.1:54320 -> 401 Unauthorized`
  - `127.0.0.1:54321/health -> 200`
- local backend port:
  - `8010` was free before probe

probe shape:

- started latest `dev` backend with:
  - `LEON_STORAGE_STRATEGY=supabase`
  - `LEON_DB_SCHEMA=staging`
  - `SUPABASE_PUBLIC_URL=http://127.0.0.1:54320`
  - `SUPABASE_AUTH_URL=http://127.0.0.1:54321`
  - `SUPABASE_ANON_KEY=<mapped from remote .env ANON_KEY>`
  - `SUPABASE_JWT_SECRET=<mapped from remote .env JWT_SECRET>`
  - `LEON_SUPABASE_SERVICE_ROLE_KEY=<mapped from remote .env SERVICE_ROLE_KEY>`
- intentionally did **not** provide `LEON_POSTGRES_URL`

observed result:

- uvicorn boot reaches:
  - `Started server process`
  - `Waiting for application startup.`
- then fail-loud exits with:
  - `RuntimeError: LEON_POSTGRES_URL is required for backend web runtime`

current classification:

- this first hard blocker is `postgres/checkpointer blocker`
- not `SQLite blocker`
- not `Supabase auth blocker`

### 机制层验证

- remote Supabase `.env` currently uses names:
  - `ANON_KEY`
  - `SERVICE_ROLE_KEY`
  - `JWT_SECRET`
- local backend code expects:
  - `SUPABASE_ANON_KEY`
  - `LEON_SUPABASE_SERVICE_ROLE_KEY`
  - `SUPABASE_JWT_SECRET`
- so current boot contract must explicitly include env-name mapping; otherwise an operator can have healthy remote Supabase secrets and still fail local bringup

### 当前 ruling（更新）

- latest `dev` already proves one important thing:
  - web startup is fail-loud about missing Postgres checkpointer contract before any late request-time ambiguity
- so the next narrowing question for `CP01` is no longer “does Supabase runtime basically boot?”
- it is:
  - where should `LEON_POSTGRES_URL` come from in the canonical local contract
  - and after supplying it, what is the next real blocker, if any

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

## 当前实现切口

- `CP01` 的第一刀实现不是直接追所有 SQLite residual
- 先修正当前 runtime entry 语义：
  - `storage.runtime.build_storage_container(...)` 已存在
  - `backend/web/core/lifespan.py` 仍直接 new `StorageContainer`
- 所以第一刀要先让 web composition root 只走 runtime entry
- 这样后续再推进 service/control-plane/middleware parity 时，正式入口才是单一的

## 第一刀实现结果

### 源码/测试层辅助证据

- [backend/web/core/lifespan.py](/Users/lexicalmathical/worktrees/leonai--supabase-strategy-entry-alignment/backend/web/core/lifespan.py)
  - 已不再直接 new `StorageContainer`
  - 改为经由 `storage.runtime.build_storage_container(...)` 获取 runtime container
- [tests/Unit/storage/test_runtime_builder_contract.py](/Users/lexicalmathical/worktrees/leonai--supabase-strategy-entry-alignment/tests/Unit/storage/test_runtime_builder_contract.py)
  - 新增 `build_storage_container(...)` 保留显式 `public_supabase_client` 的 contract
- [tests/Integration/test_storage_repo_abstraction_unification.py](/Users/lexicalmathical/worktrees/leonai--supabase-strategy-entry-alignment/tests/Integration/test_storage_repo_abstraction_unification.py)
  - `lifespan` wiring test 已更新为 authoritative runtime entry path

### 机制层验证

- `uv run pytest -q tests/Unit/storage/test_runtime_builder_contract.py tests/Integration/test_storage_repo_abstraction_unification.py`
  - `21 passed`
- `uv run ruff check backend/web/core/lifespan.py storage/runtime.py tests/Unit/storage/test_runtime_builder_contract.py tests/Integration/test_storage_repo_abstraction_unification.py`
  - `All checks passed!`
- `uv run python -m py_compile backend/web/core/lifespan.py storage/runtime.py tests/Unit/storage/test_runtime_builder_contract.py tests/Integration/test_storage_repo_abstraction_unification.py`
  - `exit 0`

### 当前 ruling（再次更新）

- 当前第一刀已经完成它该完成的事：
  - web composition root 的 runtime container 入口已经单一化
- 这不等于 Supabase parity 已完成
- 下一合法动作仍然是回到 `CP01` 的 boot contract narrowing：
  - 提供 canonical `LEON_POSTGRES_URL`
  - 然后重跑 latest `dev` backend bringup

## Stopline

- 明确启动所需 env / repo / runtime 前提
- caller-proven 区分：
  - code/contract blocker
  - auth/bootstrap blocker
  - postgres/checkpointer blocker
  - provider/runtime blocker
