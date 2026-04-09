---
title: Factory Deletion And Closure Proof
status: done
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

所以 `CP06` 现在已经 closure：`storage_factory.py` 已删除，测试面已迁移/删除，fresh source scan 只剩 negative assertions，没有 live import。

但这张卡的 closure 只证明：

- issue `#191` 这簇 bypass path 已经不再依赖 `storage_factory.py`
- 正式 composition root 重新成为主线

它不应该被过度表述成：

- “整个系统已经完全摆脱 SQLite”
- 或 “sandbox/control-plane 已经天然达到 provider parity”

## 已完成事实

- 删除 [backend/web/core/storage_factory.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/backend/web/core/storage_factory.py)
- 删除 [tests/Unit/backend/web/core/test_storage_factory.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/tests/Unit/backend/web/core/test_storage_factory.py)
- 新增 [tests/Unit/storage/test_runtime_builder_contract.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/tests/Unit/storage/test_runtime_builder_contract.py)，把原 factory-level builder contract 收回 `storage.runtime`
- 更新 [tests/Integration/test_storage_repo_abstraction_unification.py](/Users/lexicalmathical/worktrees/leonai--storage-factory-deletion-cut/tests/Integration/test_storage_repo_abstraction_unification.py)，直接证明文件已删除且 runtime builders 仍成立
- fresh source scan 结果表明 `backend/web/core/storage_factory` 只剩 negative assertions，不再有 live production/test imports
- closure proof 过程中压出并修正了一条旧误判：
  - `sandbox/lease.py` 和 `sandbox/manager.py` 的 `db_path` lifecycle 不能被粗暴并入当前 `storage.runtime`
  - 这只说明当前 builder seam 不足以承接它们，不等于它们的最终架构目标永远停在 sqlite constructor

## 证据

- targeted proof:
  - `uv run pytest -q tests/Integration/test_storage_repo_abstraction_unification.py tests/Unit/storage/test_runtime_builder_contract.py tests/Unit/sandbox/test_sandbox_manager_volume_repo.py -k 'storage_factory_module_is_deleted or make_sandbox_monitor_repo or build_panel_task_repo or build_sandbox_monitor_repo or runtime_repo_builders_use_supabase_factory or requires_runtime_config'`
  - `9 passed, 28 deselected`
- full-file proof:
  - `uv run pytest -q tests/Integration/test_storage_repo_abstraction_unification.py tests/Unit/storage/test_runtime_builder_contract.py tests/Unit/sandbox/test_sandbox_manager_volume_repo.py tests/Unit/sandbox/test_manager_repo_strategy.py tests/Unit/sandbox/test_lease_probe_contract.py`
  - `49 passed`
- lint / compile:
  - `uv run ruff check sandbox/lease.py sandbox/manager.py tests/Integration/test_storage_repo_abstraction_unification.py tests/Unit/storage/test_runtime_builder_contract.py tests/Unit/sandbox/test_sandbox_manager_volume_repo.py tests/Unit/sandbox/test_manager_repo_strategy.py tests/Unit/sandbox/test_lease_probe_contract.py`
  - `All checks passed!`
  - `uv run python -m py_compile sandbox/lease.py sandbox/manager.py tests/Integration/test_storage_repo_abstraction_unification.py tests/Unit/storage/test_runtime_builder_contract.py tests/Unit/sandbox/test_sandbox_manager_volume_repo.py tests/Unit/sandbox/test_manager_repo_strategy.py tests/Unit/sandbox/test_lease_probe_contract.py`
  - `exit 0`
- source scan:
  - `rg -n "backend\\.web\\.core\\.storage_factory|from backend\\.web\\.core import storage_factory" backend sandbox storage tests -g '*.py'`
  - only negative string assertions remain

## Stopline

- `CP06` 到这里 closure
- `#191` 的真实剩余动作不再是代码 slice，而是 stacked PR 审核/合并与最终 issue closure
- 如果后续要追求“整个系统在 `LEON_STORAGE_STRATEGY=supabase` 下无需 SQLite 也能独立运行”，那是新的 architecture lane，不应伪装成 `#191` 已自然完成
