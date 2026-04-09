---
title: Supabase-First Runtime Parity
owner: fjj
priority: P1
status: in_progress
created: 2026-04-09
---

# Supabase-First Runtime Parity

目标：把运行时主线收成“Supabase 是 canonical strategy，SQLite 只保留为显式本地 `db_path` 合同”，并用真实 caller-proof 区分哪些 checkpoint 已经闭环，哪些还只是局部对齐。

## 当前 mainline truth

这张卡现在以 `origin/dev = f0264bfdd1d204f1b0b24c924451c2097788e0c3` 为准，不再沿用 2026-04-09 早期 inventory 的旧 worktree 观察。

当前 `dev` 已经完成的事实：

- web/service composition root 已经回到 [backend/web/core/lifespan.py](backend/web/core/lifespan.py) + [storage/runtime.py](storage/runtime.py)
- `file_channel / helpers / webhooks / threads / monitor` 这些 service surface 已不再直接 new SQLite repos
- sandbox control-plane 已收口到 [sandbox/control_plane_repos.py](sandbox/control_plane_repos.py)
- queue / summary / session cleanup / command registry / terminal state 这些 runtime seam 已有 strategy-aware path

但这不等于 closure 已完成。

2026-04-10 fresh audit 的关键事实是：

- 真实 backend bringup + auth + thread/sandbox API proof 已能成立
- 真实 Daytona self-hosted 单 agent proof 暴露出一个仍未进 `dev` 的 CP03 blocker：
  - `SandboxManager._ensure_thread_volume()` 依赖 `lease_store.set_volume_id(...)`
  - `SupabaseLeaseRepo` 在 `dev` 里还缺这条合同
  - 该 fix 已单独送审于 [#396](https://github.com/OpenDCAI/Mycel/pull/396)

## 当前 ruling

- `CP00` 已不该继续标 `in_progress`
- `CP02` service surface parity 已基本收口
- 当前 mainline 最大 residual 不再是 service 层，而是 sandbox control-plane 的剩余 contract gap
- `CP05 Closure Proof` 已经开始，但还不能诚实地宣称完成

## 子任务

| # | 子任务 | 说明 | 状态 |
|---|--------|------|------|
| 00 | [Current State Inventory](subtask-00-current-state-inventory.md) | 用 current `dev` 重新分类 residual，去掉早期 stale inventory | done |
| 01 | [Supabase Boot Contract](subtask-01-supabase-boot-contract.md) | 验证 `LEON_STORAGE_STRATEGY=supabase` bringup 所需最小 contract，并记录真实 blocker 分类 | in_progress |
| 02 | [Service Surface Parity](subtask-02-service-surface-parity.md) | web/service 层 direct SQLite caller 收口 | done |
| 03 | [Sandbox Control Plane Parity](subtask-03-sandbox-control-plane-parity.md) | lease / terminal / chat-session / manager 的剩余 strategy contract gap | in_progress |
| 04 | [Default Supabase Cut](subtask-04-default-supabase-cut.md) | 默认运行面与 env-less contract 的诚实边界 | in_progress |
| 05 | [Closure Proof](subtask-05-closure-proof.md) | 高强度 caller-proof：shared sandbox / Daytona / multi-agent | in_progress |

## 当前 stopline

这张卡现在不能靠“代码里 SQLite 痕迹变少了”来 closure。真正 stopline 仍然是：

1. `LEON_STORAGE_STRATEGY=supabase` 下关键运行路径可独立成立
2. 默认本地/开发主线是 Supabase-first，或至少 ledger 明确写清 env-less 的诚实边界
3. SQLite 不再是关键 caller 的隐含必需品
4. closure 由真实产品验证 / 机制层验证 / 源码测试辅助证据共同支撑，而不是只靠局部单测

## 默认 next move

- 先合并或等价落下 [#396](https://github.com/OpenDCAI/Mycel/pull/396)
- 然后在最新 `dev` 上重跑高强度 proof：
  - shared sandbox file collaboration
  - Daytona self-hosted agent path
  - 更高层 multi-agent stress scenario
