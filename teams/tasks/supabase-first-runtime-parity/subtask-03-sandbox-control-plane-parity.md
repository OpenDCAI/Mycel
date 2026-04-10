---
title: Sandbox Control Plane Parity
status: done
created: 2026-04-09
---

# Sandbox Control Plane Parity

目标：处理 lease / terminal / chat-session / manager 等 control-plane caller 的 provider parity，避免 canonical strategy path 继续被 raw sqlite side-write 打穿。

## Current `dev` truth

当前 `dev` 上，这条子任务已经不是“从零开始”：

- [sandbox/control_plane_repos.py](sandbox/control_plane_repos.py) 已经存在
- [sandbox/chat_session.py](sandbox/chat_session.py)、[sandbox/manager.py](sandbox/manager.py)、[sandbox/lease.py](sandbox/lease.py)、[sandbox/terminal.py](sandbox/terminal.py) 都已经部分 strategy-aware

所以当前真正的 residual 不是 broad import cleanup，而是更窄的 contract gap。

## Fresh blocker

2026-04-10 的真实 Daytona self-hosted agent proof 直接打出：

- [sandbox/manager.py](sandbox/manager.py) 的 `_ensure_thread_volume()` 会调用 `lease_store.set_volume_id(...)`
- 但 `dev` 上的 [storage/providers/supabase/lease_repo.py](storage/providers/supabase/lease_repo.py) 还没有这条实现

这说明当时：

- control-plane 大面已经收过
- 但 `CP03` 还没 closure
- 当前 stopline 落在一个明确、狭窄、可验证的 contract hole 上

## Former next slice

- [#396](https://github.com/OpenDCAI/Mycel/pull/396)
  - 为 `LeaseRepo` 补 `set_volume_id(...)`
  - 为 `SupabaseLeaseRepo` 补实现
  - regression 已补

## Ruling

- [#396](https://github.com/OpenDCAI/Mycel/pull/396) 现已进入 mainline
- shared Daytona lease / file collaboration、pause / resume、destroy persistence、backend restart longevity 与三线程压力 proof 都已经成立
- `CP03` 到这里可以关卡
