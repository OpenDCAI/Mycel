---
title: Current State Inventory
status: open
created: 2026-04-09
---

# Current State Inventory

目标：固化 current `dev` 下所有仍依赖 SQLite、或仅在 SQLite 语义下成立的 runtime/service/control-plane 路径，避免后续“凭印象推进”。

## 关注点

- 直接 import `storage.providers.sqlite.*` 的 production path
- 依赖 `sandbox.db` / `db_path` 的 caller
- `LEON_STORAGE_STRATEGY=supabase` 下仍会退化到 SQLite 的路径
- 默认配置仍非 Supabase-first 的入口

## Stopline

- 给出按 owner/seam 分层的残余清单
- 明确哪些是 service surface，哪些是 sandbox control-plane，哪些是 boot/default contract
