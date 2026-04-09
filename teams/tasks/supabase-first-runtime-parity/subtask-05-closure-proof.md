---
title: Closure Proof
status: in_progress
created: 2026-04-09
---

# Closure Proof

目标：用高强度 caller-proof 证明系统在 Supabase 下可独立运行，SQLite 不再是关键路径的隐含前提。

## 当前进度

这条子任务已经开始，不该继续标 `open`。

2026-04-10 fresh audit 已经做过这些 proof：

### 真实产品验证

- 本地 backend 在完整 Supabase runtime env 下真实启动
- `POST /api/auth/login`、`POST /api/threads`、`GET /api/threads/{thread_id}/lease`、`POST /api/threads/{thread_id}/files/upload`、`GET /api/threads/{thread_id}/files/download`、`POST /api/threads/{thread_id}/messages` 都已真实回放
- 真实 Daytona self-hosted shared lease / file roundtrip 已成立：
  - `thread1 = m_dKjuBBLbR1bw-89`
  - `thread2 = m_dKjuBBLbR1bw-90`
  - `lease_id = lease-0dbeb9b21e4a`
  - `thread1` 上传 `proof-7e06d242-t1.txt` 并下载回放成功
  - `thread1` 通过附件消息触发 sync 后，`thread2` 在 `/home/daytona/files` 立刻列到并读到该文件
  - `thread2` 上传 `proof-7e06d242-t2.txt` 并触发 sync 后，`thread1` 也立刻列到并读到该文件
- 真实 Daytona self-hosted pause / resume persistence proof 已成立：
  - `thread1 = m_dKjuBBLbR1bw-91`
  - `thread2 = m_dKjuBBLbR1bw-92`
  - `lease_id = lease-903b2d85c748`
  - pause 后 lease `desired_state/observed_state` 都转为 `paused`
  - resume 后 lease 回到 `running`
  - 同一 instance id 持续复用
  - pause 前后 shared files 都能跨线程继续读取
- 真实 Daytona self-hosted destroy persistence proof 已成立：
  - `thread1 = m_dKjuBBLbR1bw-99`
  - `thread2 = m_dKjuBBLbR1bw-100`
  - `lease_id = lease-876d9e57240b`
  - `DELETE /api/threads/{thread1}/sandbox -> 200`
  - surviving `thread2` 在 destroy 后仍保持 `desired_state=running / observed_state=running`
  - destroy 前已同步的 `remote file` 在 destroy 后仍继续可读
- 真实 Daytona self-hosted backend-restart longevity proof 已成立：
  - backend A 上建立 shared lease：`thread1 = m_dKjuBBLbR1bw-101`，`thread2 = m_dKjuBBLbR1bw-102`
  - `lease_id = lease-20045fcfa4b3`
  - restart 前 `thread2` 能读到 `thread1` 同步的 `longevity-d3a3d42d-t1.txt`
  - backend A 完全退出后，backend B 冷启动
  - restart 后 `thread2` 仍能读到旧文件
  - restart 后 `thread2` 新写入并同步 `longevity-b975998d-t2.txt`，`thread1` 也能反向读到
  - cold start 初始 lease truth 一度表现为 `paused/version=4`，但在新一轮 thread activity 后收敛回 `running/version=6`
- 真实 Daytona self-hosted 三线程共享 lease 压力 proof 已成立：
  - `thread1 = m_dKjuBBLbR1bw-105`
  - `thread2 = m_dKjuBBLbR1bw-106`
  - `thread3 = m_dKjuBBLbR1bw-107`
  - `lease_id = lease-135dd60b2aa1`
  - 三个 thread 初始都绑定到同一个 detached lease
  - 第 1 轮：`thread1` 上传 `three-thread-8dcd17a0-t1.txt`，public download 成功，附件消息触发 sync 后，`thread2` 和 `thread3` 都能从 `/home/daytona/files` 读到
  - 第 2 轮：`thread2` 上传 `three-thread-8dcd17a0-t2.txt`，`thread1` 和 `thread3` 都能读到
  - 第 3 轮：`thread3` 上传 `three-thread-8dcd17a0-t3.txt`，`thread1` 和 `thread2` 都能读到
  - 最终远端 `/home/daytona/files` 列表稳定包含这 3 个文件
  - 三边 lease truth 最终一致：同一个 `instance_id = 50d883e8-ba58-4f62-886a-52881a948ad0`，`desired_state=running / observed_state=running / version=19`

### 机制层验证

- 真实 Daytona self-hosted 单 agent path 已回放
- shared Daytona lease / file collaboration 已不是“设计并实际试跑”，而是 fresh 成功 proof
- 这轮 proof 还压实了一个运行面前提：
  - fresh proof worktree 的 `.venv` 若只执行默认 `uv sync`，`daytona_sdk` 不会安装
  - 自托管 Daytona caller-proof 前需要先执行 `uv sync --extra daytona`
  - backend web runtime 还会在 startup 阶段硬要求 `LEON_POSTGRES_URL`
  - 本地若把 `LEON_POSTGRES_URL` 指向远端 host 的 `localhost:5432`，实际会打到 `supavisor` 并得到 `Tenant or user not found`
  - 真实 caller-proof 需要直通 `supabase-db` 容器的裸 Postgres，而不是复用 Supavisor 口

### 当前未 closure 的原因

proof 并没有只带来“都能跑”的结论，但先前 blocker 已经进 mainline，当前未 closure 的原因也随之变化：

- [#396](https://github.com/OpenDCAI/Mycel/pull/396) 已经补齐 `SupabaseLeaseRepo.set_volume_id(...)`
- shared lease / file roundtrip、pause / resume、destroy persistence、backend-restart longevity 与三线程共享 lease 压力场景虽已成立，但 closure 还缺更高压场景：
  - 更脏的 dirty-state / long-idle / restart-after-idle path
  - 更高层 multi-agent stress scenario

## Ruling

- `CP05` 已进入 `in_progress`
- shared Daytona lease / file collaboration、pause / resume、destroy persistence、backend-restart longevity 与三线程共享 lease 压力场景已从“机制层试跑”提升为 `真实产品验证`
- 但 closure 仍然要等更高压 proof：
  1. 更脏的 Daytona self-hosted dirty-state / long-idle / restart-after-idle path
  2. 更高层 multi-agent pressure proof

## 证据要求

- 真实产品验证
- 机制层验证
- 源码/测试层辅助证据

三者缺一不可，不能继续用局部单测替代 closure proof。
