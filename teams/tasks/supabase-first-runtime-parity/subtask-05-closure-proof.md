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
- login / threads / sandbox APIs 可调用

### 机制层验证

- 真实 Daytona self-hosted 单 agent path 已回放
- shared Daytona lease / file collaboration 已设计并实际试跑

### 当前未 closure 的原因

proof 并没有只带来“都能跑”的结论，它同时暴露了 current `dev` 的真实 blocker：

- `SupabaseLeaseRepo` 缺少 `set_volume_id(...)`
- 这会在 Daytona agent path 的 volume bootstrap 上爆出真实 contract failure
- 该 blocker 已被单独切成 [#396](https://github.com/OpenDCAI/Mycel/pull/396)

## Ruling

- `CP05` 已进入 `in_progress`
- 但 closure 仍然要等两件事：
  1. [#396](https://github.com/OpenDCAI/Mycel/pull/396) 这类 fresh blocker 进 mainline
  2. 在最新 `dev` 上重跑 shared sandbox / Daytona / 更高层 multi-agent pressure proof

## 证据要求

- 真实产品验证
- 机制层验证
- 源码/测试层辅助证据

三者缺一不可，不能继续用局部单测替代 closure proof。
