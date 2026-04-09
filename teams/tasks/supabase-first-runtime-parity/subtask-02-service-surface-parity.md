---
title: Service Surface Parity
status: open
created: 2026-04-09
---

# Service Surface Parity

目标：收 web/service 层仍然 SQLite-only 的路径，让 service surface 在 `LEON_STORAGE_STRATEGY=supabase` 下不再隐含依赖 SQLite。

## Stopline

- service layer 不再通过 SQLite stopgap 维持运行
- 变更按小簇切，不把 sandbox/control-plane 混进同一刀
