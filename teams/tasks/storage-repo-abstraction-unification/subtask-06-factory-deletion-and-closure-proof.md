---
title: Factory Deletion And Closure Proof
status: open
created: 2026-04-09
---

# Factory Deletion And Closure Proof

终局才是删除 `backend/web/core/storage_factory.py`，并做 closure proof。

## 当前 ruling

前置切片已经全部落地：

- `CP01` panel/task service
- `CP02` resource surfaces
- `CP03` monitor operator
- `CP04` web file/helper
- `CP05` runtime-owned webhooks / lease / threads / manager

所以 `CP06` 只会在最后一个 live production callsite 收掉之后进入；当前还不是直接删文件的时候。

## 当前还没做

- 删除 [storage_factory.py](/Users/lexicalmathical/worktrees/leonai--storage-sandbox-manager-cut/backend/web/core/storage_factory.py)
- 跑一轮 source scan / targeted proof，确认 live production callsites 已经不再依赖它
- 判断是否只剩测试面保留，还是连测试 helper 也要一起收
- 先清掉当前仍然存在的 live residual：
  - [sandbox_service.py](/Users/lexicalmathical/worktrees/leonai--storage-sandbox-manager-cut/backend/web/services/sandbox_service.py)
