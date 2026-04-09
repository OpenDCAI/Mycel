---
title: Supabase-First Runtime Parity
owner: fjj
priority: P1
status: in_progress
created: 2026-04-09
---

# Supabase-First Runtime Parity

目标：把当前仍然直接依赖 SQLite、或只在 SQLite 语义下成立的运行路径，继续推进到 `LEON_STORAGE_STRATEGY=supabase` 可独立运行的状态，并把默认运行面收成 Supabase-first，而不是继续让系统名义上支持多数据库、实际上某些关键路径仍然隐含依赖 SQLite。

## 背景

`#191` 已完成的是抽象层 closure：

- `storage_factory.py` 已删除
- issue 点名的 bypass repos 已回到正式 composition root

但这不等于系统已经达到下一层目标：

- `LEON_STORAGE_STRATEGY=supabase` 下无需 SQLite 也能独立运行
- 默认配置就是 Supabase
- storage abstraction 不再被局部 SQLite 直连打穿

当前 `origin/dev` 仍然能看到一批 SQLite 直接依赖或 SQLite-only 语义：

- [backend/web/services/file_channel_service.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/backend/web/services/file_channel_service.py)
- [sandbox/chat_session.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/chat_session.py)
- [sandbox/lease.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/lease.py)
- [sandbox/manager.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/sandbox/manager.py)

用户已明确重新钉死最终 invariant：

- 系统最终必须可以只靠 Supabase 跑起来
- 默认配置应该就是 Supabase
- 同时保留多数据库抽象

## 当前 ruling

- 这条 lane 不是 `#191` 的继续加码，而是 `#191` 之后的新主任务
- 第一阶段不急着写实现，先把“哪些路径仍然 SQLite-only、哪些只是临时 stopgap、哪些已经 strategy-aware”分层盘清
- 只有在分层完成后，才开最小 implementation slices
- 第一轮 inventory 已经确认：
  - `backend/web/core/lifespan.py` 本身已经是 Supabase-first composition root
  - 当前主要残余集中在 file channel、sandbox control-plane、session/checkpoint side-store、queue/summary middleware
- 第一刀 implementation slice 已收窄为：
  - 不扩 provider parity write set
  - 先把已有 `storage.runtime.build_storage_container(...)` 提升成 authoritative runtime entry
  - 再让 `backend/web/core/lifespan.py` 改为只经由 runtime entry 取 container
  - 目的不是新功能，而是先把 `StorageContainer` 与 `storage.runtime` 的语义对齐
- 当前这刀已完成：
  - `backend/web/core/lifespan.py` 已改为只经由 `storage.runtime.build_storage_container(...)` 获取 runtime container
  - 对应 unit/integration contract tests 已补齐并通过
  - SQLite residual 仍保持原边界，未在本刀扩写

## 子任务

| # | 子任务 | 说明 | 状态 |
|---|--------|------|------|
| 00 | [Current State Inventory](subtask-00-current-state-inventory.md) | 固化 current `dev` 下所有仍依赖 SQLite 的 runtime/service/control-plane 路径 | in_progress |
| 01 | [Supabase Boot Contract](subtask-01-supabase-boot-contract.md) | 定义并验证 `LEON_STORAGE_STRATEGY=supabase` 下系统独立启动所需最小 contract | done |
| 02 | [Service Surface Parity](subtask-02-service-surface-parity.md) | 收 web/service 层仍然 SQLite-only 的路径 | open |
| 03 | [Sandbox Control Plane Parity](subtask-03-sandbox-control-plane-parity.md) | 收 sandbox lease/terminal/chat-session/manager 等 control-plane seam | open |
| 04 | [Default Supabase Cut](subtask-04-default-supabase-cut.md) | 把默认运行面收成 Supabase-first | open |
| 05 | [Closure Proof](subtask-05-closure-proof.md) | 真实证明系统在 Supabase 下可独立运行，SQLite 不再是隐含前提 | open |

## 边界

- 不把这条 lane 伪装成 `#191` 的自然尾巴
- 不靠“保留 SQLite stopgap”来假装 provider parity
- 不一上来重写整个 sandbox/runtime 架构
- 每一刀都要显式区分：
  - 真实产品验证
  - 机制层验证
  - 源码/测试层辅助证据

## Stopline

这条任务 closure 的标准是：

1. `LEON_STORAGE_STRATEGY=supabase` 下关键运行路径可独立成立
2. 默认本地/开发主线配置是 Supabase-first
3. SQLite 不再是某些关键路径的隐含必需品
4. 多数据库抽象仍保留，不把业务层写死成 Supabase-only

## Default Next Move

- `CP02 Service Surface Parity`
  - 先处理 web/service 层仍然 SQLite-only 的最窄 caller
  - 优先从 `backend/web/services/file_channel_service.py` 起刀
  - 目标是把 service surface 的 SQLite 直连继续收回正式 storage strategy 链
