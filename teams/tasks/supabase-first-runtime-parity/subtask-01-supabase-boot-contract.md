---
title: Supabase Boot Contract
status: in_progress
created: 2026-04-09
---

# Supabase Boot Contract

目标：定义并验证 `LEON_STORAGE_STRATEGY=supabase` 下系统独立启动所需的最小 contract，并把失败精确分类，而不是继续把所有 bringup 问题糊成“还是依赖 SQLite”。

## Fresh audit facts

2026-04-10 的真实 bringup / API proof 已经拿到这些事实：

- 只要给出完整 Supabase runtime env + tenant-aware `LEON_POSTGRES_URL`，backend 可以真实启动
- 登录与基础 API caller-proof 已成立：
  - `POST /api/auth/login`
  - `GET /api/threads`
  - `GET /api/sandbox/leases/mine`
  - `GET /api/sandbox/types`
- 这说明 boot contract 已经不再停留在“理论上应该可以”

## 当前 blocker 分类

当前未 closure 的部分，不应再归因到 boot root 本身：

- code / contract blocker
  - sandbox control-plane strategy path 仍缺 `LeaseRepo.set_volume_id(...)`
  - 已单独送审于 [#396](https://github.com/OpenDCAI/Mycel/pull/396)
- provider / runtime blocker
  - Daytona self-hosted provider proof仍需持续回放
- auth / bootstrap blocker
  - 当前不再是主 blocker
- postgres / checkpointer blocker
  - tenant-aware DSN 是 bringup 前提，不能再沿用旧 `postgres@127.0.0.1:5432` 假设

## 当前 ruling

- `lifespan` 和 runtime storage builder 已足够支持 Supabase bringup
- `CP01` 还不能关，因为高层 provider path 仍会把真实 blocker 暴露出来
- 但它也不该继续写成“刚开始定义 contract”

## Default next move

- 合并 [#396](https://github.com/OpenDCAI/Mycel/pull/396) 后
- 用同一套真实 env 再跑一轮 backend + Daytona agent proof
- 若失败，再继续按 blocker 分类推进，而不是回退成 broad inventory
