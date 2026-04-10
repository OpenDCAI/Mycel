---
title: Supabase-First Runtime Parity
owner: fjj
priority: P1
status: done
created: 2026-04-09
---

# Supabase-First Runtime Parity

目标：把运行时主线收成“Supabase 是 canonical strategy，SQLite 只保留为显式本地 `db_path` 合同”，并用真实 caller-proof 区分哪些 checkpoint 已经闭环，哪些还只是局部对齐。

## 当前 mainline truth

这张卡现在以 `origin/dev = 72aa80e610de869bb014af84158fc0a7ba30aafa` 为准，不再沿用 2026-04-09 早期 inventory 的旧 worktree 观察。

当前 `dev` 已经完成的事实：

- web/service composition root 已经回到 [backend/web/core/lifespan.py](backend/web/core/lifespan.py) + [storage/runtime.py](storage/runtime.py)
- `file_channel / helpers / webhooks / threads / monitor` 这些 service surface 已不再直接 new SQLite repos
- sandbox control-plane 已收口到 [sandbox/control_plane_repos.py](sandbox/control_plane_repos.py)
- queue / summary / session cleanup / command registry / terminal state 这些 runtime seam 已有 strategy-aware path

这张卡现在已经可以 closure。

2026-04-10 fresh audit / proof 后、并结合已经进 mainline 的 `#401 ~ #404`，关键事实是：

- 真实 backend bringup + auth + thread/sandbox API proof 已能成立
- [#396](https://github.com/OpenDCAI/Mycel/pull/396) 已进 mainline，`SupabaseLeaseRepo.set_volume_id(...)` contract gap 已补齐
- shared Daytona lease / file collaboration 的真实产品级 proof 已成立：
  - `thread1` 创建 `daytona_selfhost` 线程并拿到 lease
  - `thread2` 通过 `lease_id` 绑定同一 lease
  - `thread1` 上传附件并通过 `POST /api/threads/{thread_id}/messages` 触发 sync
  - `thread2` 立刻在 `/home/daytona/files` 读到 `thread1` 的文件
  - `thread2` 再上传自己的文件并触发 sync 后，`thread1` 也能反向读到
- shared Daytona lease 的 pause / resume persistence proof 也已成立：
  - pause 后 lease `desired_state/observed_state` 都转到 `paused`
  - resume 后 lease 回到 `running`
  - 同一 instance id 保持不变
  - pause 前同步进去的文件在 resume 后仍可跨线程读取
- shared Daytona lease 的 destroy persistence proof 也已成立：
  - `thread1` destroy 自己的 sandbox 后，surviving `thread2` 不再被一起拖进 destroyed lease
  - `thread2` 仍保持 `desired_state=running / observed_state=running`
  - destroy 前已同步的 remote file 在 destroy 后仍可继续读取
- shared Daytona lease 的 backend-restart longevity proof 已成立：
  - backend A 建立 shared lease 并同步 `thread1` 文件后完全退出
  - backend B 冷启动后，旧 `thread2` 仍能读到 restart 前的 remote file
  - `thread2` 在 restart 后继续上传并同步新文件，`thread1` 也能反向读到
  - cold start 初始 lease truth 一度表现为 `paused`，但在新一轮 thread activity 后收敛回 `running`
- shared Daytona lease 的三线程压力 proof 已成立：
  - `thread1 = m_dKjuBBLbR1bw-105`
  - `thread2 = m_dKjuBBLbR1bw-106`
  - `thread3 = m_dKjuBBLbR1bw-107`
  - `lease_id = lease-135dd60b2aa1`
  - 三轮 `upload -> public download -> attachment sync -> cross-thread remote read` 全部成功
  - 远端 `/home/daytona/files` 最终稳定包含 3 个线程各自同步的文件
  - 三边 lease truth 最终一致：同一个 `instance_id`，`desired_state=running / observed_state=running / version=19`
- 这次 proof 还暴露出一个运行面前提：
  - fresh proof worktree 若只做默认 `uv sync`，`daytona_sdk` 不会进入 `.venv`
  - 自托管 Daytona caller-proof 需要先执行 `uv sync --extra daytona`
  - fresh backend web caller-proof 还需要显式 `LEON_POSTGRES_URL`
  - 远端 Supabase host `localhost:5432` 实际是 `supavisor`，不是裸 `supabase-db`
  - 要让 backend web runtime 通过 checkpointer contract，本地需要直通 `supabase-db` 的 Postgres tunnel，而不是复用 Supavisor 口
- [#403](https://github.com/OpenDCAI/Mycel/pull/403) 已进 mainline，web shutdown 不再错误清理远端 shared sandbox
- [#404](https://github.com/OpenDCAI/Mycel/pull/404) 已进 mainline，chat delivery 在存在 live child thread 时不再回退到 stale main thread

这些事实合在一起，已经把这张卡的 stopline 推到了完成态，而不是“还差最后一点感觉上的高压 proof”。

## 当前 ruling

- `CP00 ~ CP05` 现在都已经有 mainline truth 支撑，可以统一关卡
- 当前剩余 SQLite 痕迹不再属于这张卡的 honest residual；它们要么是显式本地 `db_path` 合同，要么属于别的顶层 lane
- 这张卡不能再继续保持 `in_progress` 只是因为“也许还能做更高压 proof”

## 子任务

| # | 子任务 | 说明 | 状态 |
|---|--------|------|------|
| 00 | [Current State Inventory](subtask-00-current-state-inventory.md) | 用 current `dev` 重新分类 residual，去掉早期 stale inventory | done |
| 01 | [Supabase Boot Contract](subtask-01-supabase-boot-contract.md) | 验证 `LEON_STORAGE_STRATEGY=supabase` bringup 所需最小 contract，并记录真实 blocker 分类 | done |
| 02 | [Service Surface Parity](subtask-02-service-surface-parity.md) | web/service 层 direct SQLite caller 收口 | done |
| 03 | [Sandbox Control Plane Parity](subtask-03-sandbox-control-plane-parity.md) | lease / terminal / chat-session / manager 的剩余 strategy contract gap | done |
| 04 | [Default Supabase Cut](subtask-04-default-supabase-cut.md) | 默认运行面与 env-less contract 的诚实边界 | done |
| 05 | [Closure Proof](subtask-05-closure-proof.md) | 高强度 caller-proof：shared sandbox / Daytona / multi-agent | done |

## 当前 stopline

这张卡的真正 stopline 是：

1. `LEON_STORAGE_STRATEGY=supabase` 下关键运行路径可独立成立
2. 默认本地/开发主线是 Supabase-first，或至少 ledger 明确写清 env-less 的诚实边界
3. SQLite 不再是关键 caller 的隐含必需品
4. closure 由真实产品验证 / 机制层验证 / 源码测试辅助证据共同支撑，而不是只靠局部单测

当前这四条都已满足。

## Checkpoint hindsight

- 这张卡真正 closure 的关键，不是“彻底消灭 SQLite 字样”，而是把 canonical Supabase path 和显式本地 path 的边界讲清并做成 caller-proof。
- 以后如果要继续推进更高压 Daytona / multi-agent 场景，应当新开 proof lane，而不是让这张已经完成的 parity 卡永久挂着 `in_progress`。
