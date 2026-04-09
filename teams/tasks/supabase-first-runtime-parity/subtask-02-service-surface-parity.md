---
title: Service Surface Parity
status: done
created: 2026-04-09
---

# Service Surface Parity

目标：让 web/service 层在 `LEON_STORAGE_STRATEGY=supabase` 下不再依赖 direct SQLite caller。

## Current `dev` truth

这条子任务现在不该继续标 `open`。`origin/dev = f0264bfd` 上，关键 service surface 已经回到 runtime / control-plane seam：

- [backend/web/services/file_channel_service.py](backend/web/services/file_channel_service.py)
- [backend/web/services/monitor_service.py](backend/web/services/monitor_service.py)
- [backend/web/utils/helpers.py](backend/web/utils/helpers.py)
- [backend/web/routers/webhooks.py](backend/web/routers/webhooks.py)
- [backend/web/routers/threads.py](backend/web/routers/threads.py)

这些路径当前的共同点是：

- 不再 direct import `SQLite*Repo`
- repo dispatch 已下沉到 [storage/runtime.py](storage/runtime.py) 或 [sandbox/control_plane_repos.py](sandbox/control_plane_repos.py)

## Ruling

- `CP02` 可以关
- 后续如果 service 层再暴露新问题，应按新的 bounded slice 记账，不再把它们挂回这张子卡上
