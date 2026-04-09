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

## Remaining

- 第二轮已完成：
  - `sandbox.manager.py`
  - `sandbox.chat_session.py`
  - 两者不再各自直接 import `SQLiteChatSessionRepo / SQLiteLeaseRepo / SQLiteTerminalRepo`
  - 当前统一改走 `sandbox.control_plane_repos`
- 这说明 control-plane 的 sqlite repo construction 已经收口成单一 seam，但更深的 lease-store / sqlite connection contract 仍然存在

## Default Next Move

- 优先继续收窄 `sandbox/lease.py`
- 不直接改 `monitor_service.py`
- 下一刀要先回答：`sandbox.lease.py` 里哪些 lease-store contract 是真正必须保留的 local runtime persistence，哪些才该提升到 strategy/container seam

## Stopline

- 不把 stopgap 描述成终局
- 每一刀都先回答 owner boundary，再做实现
