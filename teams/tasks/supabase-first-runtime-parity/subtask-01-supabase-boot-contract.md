---
title: Supabase Boot Contract
status: open
created: 2026-04-09
---

# Supabase Boot Contract

目标：定义并验证 `LEON_STORAGE_STRATEGY=supabase` 下系统独立启动所需的最小 contract，不再把 SQLite 当成隐含前提。

## Stopline

- 明确启动所需 env / repo / runtime 前提
- caller-proven 区分：
  - code/contract blocker
  - auth/bootstrap blocker
  - postgres/checkpointer blocker
  - provider/runtime blocker
