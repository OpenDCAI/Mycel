---
title: Supabase Boot Contract
status: done
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

当前未 closure 的部分，已经不再归因到 boot root 本身，并且其中关键 code gap 也已经进 mainline：

- code / contract blocker
  - sandbox control-plane strategy path 仍缺 `LeaseRepo.set_volume_id(...)`
  - 该 gap 已由 [#396](https://github.com/OpenDCAI/Mycel/pull/396) 补齐并进入 mainline
- provider / runtime blocker
  - Daytona self-hosted provider proof仍需持续回放
- auth / bootstrap blocker
  - 当前不再是主 blocker
- postgres / checkpointer blocker
  - tenant-aware DSN 是 bringup 前提，不能再沿用旧 `postgres@127.0.0.1:5432` 假设

## 当前 ruling

- `lifespan` 和 runtime storage builder 已足够支持 Supabase bringup
- 高层 provider path 的真实问题已经被拆分并收进后续 checkpoint / proof，不再构成 `CP01` 本身的未 closure 理由
- `CP01` 到这里可以关卡

## Closure note

- 后续 proof 可以继续加压，但那属于 closure 之后的运行面验证，不再属于 boot contract 本身
