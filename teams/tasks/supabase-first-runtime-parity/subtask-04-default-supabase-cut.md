---
title: Default Supabase Cut
status: in_progress
created: 2026-04-09
---

# Default Supabase Cut

目标：把默认运行面与 env-less 语义写成诚实合同，而不是继续把“名义上的 Supabase-first”与“实际未配置 runtime client 的本地路径”混成一个布尔值。

## Current `dev` truth

当前 `dev` 已经有这些事实：

- [storage/runtime.py](storage/runtime.py) 的 `current_storage_strategy()` 默认名义上是 `supabase`
- 但 `uses_supabase_runtime_defaults()` 只有在显式 `LEON_STORAGE_STRATEGY=supabase`，或存在 `LEON_SUPABASE_CLIENT_FACTORY` 时才返回真

这意味着：

- 默认名义 strategy 与真正可用的 runtime defaults 不是一回事
- 当前系统已经不再粗暴地把 env-less path 全部扳成 Supabase
- 但这张卡也还不能宣称“default cut 已完全 caller-proven”

## Ruling

- `CP04` 不能再按旧卡那样写成 `open`
- 也不能过度宣称 `done`
- 当前更诚实的状态是 `in_progress`

## Stopline

- documented/default contract 与 runtime truth 不再互相打脸
- env-less path、显式 `supabase` path、显式本地 `db_path` path 的边界都有 caller-proof
