---
title: Sandbox Control Plane Parity
status: in_progress
created: 2026-04-09
---

# Sandbox Control Plane Parity

目标：处理 sandbox lease / terminal / chat-session / manager 等 control-plane caller 的 provider parity，避免它们继续成为 SQLite-only 岛。

## Current Ruling

- `backend/web/services/sandbox_service.py` 已不再是普通 service-surface repo seam。
- 当前残余的真实 owner boundary 是：
  - `SandboxManager(provider=p, db_path=SANDBOX_DB_PATH)`
  - 以及与之配套的 sandbox lease / terminal / chat-session local stores
- 这说明 `sandbox_service.py` 的 SQLite residual 不是单独一个 import 可以诚实切掉的问题，而是 `SandboxManager` control-plane contract 仍然要求本地 `sandbox.db`。
- 因此第一轮不直接写实现，而先把这条 boundary 明确钉住，避免把 `monitor_service.py` / `sandbox_service.py` 错当成 `CP02` 的延续小刀。

## First Slice

- `backend/web/services/sandbox_service.py`
  - 不再 import `storage.providers.sqlite.kernel`
  - 不再自己定义 `SANDBOX_DB_PATH`
  - 不再在 `SandboxManager(...)` 构造处显式传 `db_path`
  - `sandbox.db` 的默认 owner 下沉回 `SandboxManager`

## Evidence

- `机制层验证`
  - `uv run pytest -q tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py tests/Integration/test_sandbox_router_user_shell.py -k 'sandbox_service or list_user_leases or available_sandbox_types or sandbox_types'`
    - `7 passed, 2 deselected`
  - `uv run pytest -q tests/Unit/sandbox/test_manager_repo_strategy.py tests/Unit/core/test_runtime.py -k 'chat_session or sandbox_manager or lookup_sandbox_for_thread or bind_thread_to_existing_lease or resolve_existing_lease_cwd'`
    - `10 passed, 29 deselected`
- `源码/测试层辅助证据`
  - `uv run ruff check backend/web/services/sandbox_service.py tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py tests/Integration/test_sandbox_router_user_shell.py`
    - `All checks passed!`
  - `uv run python -m py_compile backend/web/services/sandbox_service.py tests/Unit/sandbox/test_sandbox_user_leases.py tests/Unit/sandbox/test_sandbox_provider_availability.py tests/Integration/test_sandbox_router_user_shell.py`
    - `exit 0`
  - `uv run ruff check sandbox/control_plane_repos.py sandbox/manager.py sandbox/chat_session.py tests/Unit/sandbox/test_manager_repo_strategy.py tests/Unit/core/test_runtime.py`
    - `All checks passed!`
  - `uv run python -m py_compile sandbox/control_plane_repos.py sandbox/manager.py sandbox/chat_session.py tests/Unit/sandbox/test_manager_repo_strategy.py tests/Unit/core/test_runtime.py`
    - `exit 0`
  - `uv run pytest -q tests/Unit/sandbox/test_lease_probe_contract.py tests/Unit/core/test_capability_async.py -k 'sandbox_lease or ensure_active_instance or local_sandbox_rebuilds_stale_closed_capability_before_execute_async'`
    - `3 passed, 5 deselected`
  - `uv run pytest -q tests/Unit/storage/test_supabase_lease_repo.py tests/Unit/sandbox/test_lease_probe_contract.py tests/Unit/core/test_capability_async.py tests/Unit/core/test_runtime.py -k 'lease or sandbox_lease or local_sandbox_rebuilds_stale_closed_capability_before_execute_async or lookup_sandbox_for_thread or bind_thread_to_existing_lease or resolve_existing_lease_cwd'`
    - `11 passed, 31 deselected`
  - `uv run ruff check sandbox/lease.py tests/Unit/sandbox/test_lease_probe_contract.py tests/Unit/core/test_capability_async.py`
    - `All checks passed!`
  - `uv run ruff check storage/contracts.py storage/providers/sqlite/lease_repo.py storage/providers/supabase/lease_repo.py sandbox/lease.py tests/Unit/storage/test_supabase_lease_repo.py tests/Unit/sandbox/test_lease_probe_contract.py`
    - `All checks passed!`
  - `uv run python -m py_compile sandbox/lease.py tests/Unit/sandbox/test_lease_probe_contract.py tests/Unit/core/test_capability_async.py`
    - `exit 0`
  - `uv run python -m py_compile storage/contracts.py storage/providers/sqlite/lease_repo.py storage/providers/supabase/lease_repo.py sandbox/lease.py tests/Unit/storage/test_supabase_lease_repo.py tests/Unit/sandbox/test_lease_probe_contract.py`
    - `exit 0`

## Remaining

- 第二轮已完成：
  - `sandbox.manager.py`
  - `sandbox.chat_session.py`
  - 两者不再各自直接 import `SQLiteChatSessionRepo / SQLiteLeaseRepo / SQLiteTerminalRepo`
  - 当前统一改走 `sandbox.control_plane_repos`
- 第三轮已完成：
  - `sandbox.lease.py`
  - 不再直接 import `SQLiteLeaseRepo`
  - lease-store construction 也已收口到 `sandbox.control_plane_repos`
- 第四轮已完成：
  - `storage/contracts.py::LeaseRepo`
  - `storage/providers/sqlite/lease_repo.py`
  - `storage/providers/supabase/lease_repo.py`
  - `sandbox/lease.py:_record_provider_error()`
  - 现已补入 `persist_metadata(...)` 写面
  - 且 `sandbox.lease.py` 在 `LEON_STORAGE_STRATEGY=supabase` 下会通过 `storage.runtime.build_lease_repo(...)` 取 lease repo，而不再继续沿用本地 sqlite lease-store builder
- 这说明 control-plane 的 sqlite repo construction 已经收口成单一 seam，但更深的 lease-store / sqlite connection contract 仍然存在

## Next Ruling

- `sandbox.lease.py` 当前剩余的 sqlite dependency 已不是 import 级别，而是 state-machine write 级别：
  - `_connect`
  - `_append_event`
  - `_persist_snapshot`
  - `_persist_lease_metadata`
- 这些路径直接写：
  - `sandbox_leases`
  - `sandbox_instances`
  - `lease_events`
- 当前 `storage.providers.supabase.lease_repo.SupabaseLeaseRepo` 只覆盖了更窄的 CRUD / adopt / refresh 面，还没有承接这组 state-machine writes。
- 因此下一刀如果继续，必须先回答是否要把 lease snapshot / event append contract 正式提升进 repo seam；这已经不是“继续清理 SQLite import”。

## Contract Gap

- 当前 `storage/contracts.py::LeaseRepo` 只声明：
  - `get`
  - `create`
  - `find_by_instance`
  - `adopt_instance`
  - `mark_needs_refresh`
  - `delete`
  - `list_all`
  - `list_by_provider`
- 但 `sandbox/lease.py` 的 state machine 仍然需要更深的 write surface：
  - lease snapshot persistence
  - detached / active instance row persistence
  - lease event append
  - metadata-only persistence on error paths
- 所以下一刀如果继续，应该先扩 `LeaseRepo` contract，而不是再做 caller-level import cleanup。

## Latest Slice

- 当前最小实现已经补了一条真实 contract：
  - `LeaseRepo.persist_metadata(...)`
- 这条 contract 当前只迁移了一个 caller：
  - `SQLiteLease._record_provider_error()`
- 这刀的作用不是“完成 lease parity”，而是把最明显的假 parity 收成真 parity：
  - 之前 Supabase strategy 下这里只会写 `mark_needs_refresh`
  - `last_error / version / observed_at / status` 等 metadata 并不会真正进入 strategy repo
  - 现在这条路径已经会通过 strategy lease repo 持久化完整 metadata 并 reload row truth

## Default Next Move

- 不直接改 `monitor_service.py`
- 不继续追加零碎 metadata/import 清理
- 下一刀要先回答高层 `lease transition` contract，而不是继续暴露底层 sqlite plumbing
- 推荐优先设计一个单一高层 seam，例如：
  - `apply_transition(...)`
  - 而不是直接把 `_persist_snapshot / _append_event / _persist_lease_metadata` 原样抬进 protocol

## Stopline

- 不把 stopgap 描述成终局
- 每一刀都先回答 owner boundary，再做实现
