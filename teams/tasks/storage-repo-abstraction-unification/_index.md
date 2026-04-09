---
title: Storage Repo Abstraction Unification
owner: fjj
priority: P1
status: open
created: 2026-04-09
issue: 191
---

# Storage Repo Abstraction Unification

目标：把 `#191` 里仍残留的 `backend/web/core/storage_factory.py` 临时桥逐簇收回正式主线，让 repo 选择统一落在 `storage/contracts.py -> storage/container.py -> storage.runtime / explicit injection`，而不是继续在 web/service/helper 边角各自 new provider。

## 当前 ruling

- `storage_factory.py` 仍是 live production bridge
- `CP01` 已完成：`task_service / cron_job_service` 默认路径已离开 `storage_factory.py`
- `CP02` 已完成：`resource_service / resource_projection_service` 已离开 `storage_factory.py`
- 当前最危险 residual 是 `monitor_service` 的 split-brain correctness seam

## 子任务

| # | 子任务 | 说明 | 状态 |
|---|--------|------|------|
| 00 | [Current State & Stopline](subtask-00-current-state-and-stopline.md) | 固化 current `dev` 与 issue 的真实差距 | done |
| 01 | [Web Service Injection Cut](subtask-01-web-service-injection-cut.md) | 先收 `task_service / cron_job_service` | done |
| 02 | [Resource Surfaces Cut](subtask-02-resource-surfaces-cut.md) | 再收 `resource_service / resource_projection_service` | done |
| 03 | [Monitor Operator Cut](subtask-03-monitor-operator-cut.md) | 单独收 `monitor_service` split-brain seam | open |
| 04 | [Web Thread/File Helper Cut](subtask-04-web-thread-file-helper-cut.md) | 收 thread/file/webhook helpers | open |
| 05 | [Sandbox Runtime Owner Cut](subtask-05-sandbox-runtime-owner-cut.md) | 最后处理 runtime-owned builder residuals | open |
| 06 | [Factory Deletion And Closure Proof](subtask-06-factory-deletion-and-closure-proof.md) | 删除 `storage_factory.py` 并做 closure proof | open |

## 边界

- 不继续给 `storage_factory.py` 添能力
- 不把 `CP02` 和 `monitor_service` 混成一刀
- 不顺手改 monitor/resource payload 语义
- 每一刀只搬一小簇 callsite，然后回到真实 proof

