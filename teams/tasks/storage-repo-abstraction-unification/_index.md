---
title: Storage Repo Abstraction Unification
owner: fjj
priority: P1
status: done
created: 2026-04-09
issue: 191
---

# Storage Repo Abstraction Unification

目标：把 `#191` 里仍残留的 `backend/web/core/storage_factory.py` 临时桥逐簇收回正式主线，让 issue 点名的 bypass repos 回到 `storage/contracts.py -> storage/container.py -> backend/web/core/lifespan.py / storage.runtime / explicit injection` 这条正式 composition root，而不是继续在 web/service/helper 边角各自 new provider。

## 当前 ruling

- `CP01` 到 `CP06` 已全部实现
- `backend/web/core/storage_factory.py` 已删除
- fresh source scan 下只剩 negative assertions，不再有 live production/test imports
- 这条任务的 closure 只证明 issue `#191` 这簇 bypass path 已回到正式 composition root
- 它不自动证明整个 sandbox/control-plane 已达到“无需 SQLite 也能独立跑”的最终架构
- `sandbox/lease.py` / `sandbox/manager.py` 这类 `db_path` caller 在本轮里只是为了删桥做最小收口；是否继续推进到完整 strategy/container 语义，不在 `#191` 的 closure 里宣称完成
- `#373` 已 merged：
  - merge commit: `48e44b22aea32570749c9715b20e9b78e4c72d60`

## 子任务

| # | 子任务 | 说明 | 状态 |
|---|--------|------|------|
| 00 | [Current State & Stopline](subtask-00-current-state-and-stopline.md) | 固化 current `dev` 与 issue 的真实差距 | done |
| 01 | [Web Service Injection Cut](subtask-01-web-service-injection-cut.md) | 先收 `task_service / cron_job_service` | done |
| 02 | [Resource Surfaces Cut](subtask-02-resource-surfaces-cut.md) | 再收 `resource_service / resource_projection_service` | done |
| 03 | [Monitor Operator Cut](subtask-03-monitor-operator-cut.md) | 单独收 `monitor_service` split-brain seam | done |
| 04 | [Web Thread/File Helper Cut](subtask-04-web-thread-file-helper-cut.md) | `CP04a file/helper` + `CP04b helpers` 已完成，threads/webhooks 已转入 `CP05` | done |
| 05 | [Sandbox Runtime Owner Cut](subtask-05-sandbox-runtime-owner-cut.md) | `CP05a webhooks` + `CP05b sandbox/lease` + `CP05c threads bootstrap` + `CP05d manager` + `CP05e sandbox_service` 已完成 | done |
| 06 | [Factory Deletion And Closure Proof](subtask-06-factory-deletion-and-closure-proof.md) | 删除 `storage_factory.py` 并做 closure proof | done |

## 边界

- 不继续给 `storage_factory.py` 添能力
- 不把 `CP02` 和 `monitor_service` 混成一刀
- 不顺手改 monitor/resource payload 语义
- 不把 sandbox/control-plane stopgap 写成 `#191` 的最终架构胜利
- 每一刀只搬一小簇 callsite，然后回到真实 proof

## Checkpoint hindsight

- `删桥` 和 `全域 provider parity` 不是同一条任务
- `#191` 的诚实 closure 是：issue 点名的 bypass repos 重新回到正式 composition root
- 如果目标升级成“系统可在 `LEON_STORAGE_STRATEGY=supabase` 下独立运行、默认即 Supabase”，那必须单独立新 lane，不能在 `#191` 的 closure 里偷换完成
