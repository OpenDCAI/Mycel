from pathlib import Path

import pytest

from storage import StorageContainer
from storage.providers.sqlite.checkpoint_repo import SQLiteCheckpointRepo
from storage.providers.sqlite.eval_repo import SQLiteEvalRepo
from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo
from storage.providers.supabase.checkpoint_repo import SupabaseCheckpointRepo
from storage.providers.supabase.eval_repo import SupabaseEvalRepo
from storage.providers.supabase.file_operation_repo import SupabaseFileOperationRepo
from storage.providers.supabase.run_event_repo import SupabaseRunEventRepo
from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from storage.providers.supabase.summary_repo import SupabaseSummaryRepo


class _FakeSupabaseClient:
    def table(self, table_name: str):
        raise AssertionError(f"table() should not be called in this container test: {table_name}")


def test_storage_container_sqlite_strategy_uses_sqlite_checkpoint_repo(tmp_path: Path) -> None:
    container = StorageContainer(main_db_path=tmp_path / "leon.db", strategy="sqlite")
    assert isinstance(container.checkpoint_repo(), SQLiteCheckpointRepo)


def test_storage_container_supabase_strategy_builds_concrete_repos() -> None:
    container = StorageContainer(strategy="supabase", supabase_client=_FakeSupabaseClient())

    assert isinstance(container.checkpoint_repo(), SupabaseCheckpointRepo)
    assert isinstance(container.run_event_repo(), SupabaseRunEventRepo)
    assert isinstance(container.file_operation_repo(), SupabaseFileOperationRepo)
    assert isinstance(container.summary_repo(), SupabaseSummaryRepo)
    assert isinstance(container.eval_repo(), SupabaseEvalRepo)
    assert isinstance(container.sandbox_monitor_repo(), SupabaseSandboxMonitorRepo)


def test_storage_container_sqlite_strategy_builds_sqlite_sandbox_monitor_repo(tmp_path: Path) -> None:
    container = StorageContainer(main_db_path=tmp_path / "leon.db", strategy="sqlite")
    assert isinstance(container.sandbox_monitor_repo(), SQLiteSandboxMonitorRepo)


@pytest.mark.parametrize(
    ("strategy", "repo_providers", "repo_method", "expected_type"),
    [
        ("sqlite", {"checkpoint_repo": "supabase"}, "checkpoint_repo", SupabaseCheckpointRepo),
        ("supabase", {"eval_repo": "sqlite"}, "eval_repo", SQLiteEvalRepo),
    ],
)
def test_storage_container_repo_level_overrides(
    strategy: str,
    repo_providers: dict[str, str],
    repo_method: str,
    expected_type: type,
) -> None:
    container = StorageContainer(
        strategy=strategy,
        repo_providers=repo_providers,
        supabase_client=_FakeSupabaseClient(),
    )
    assert isinstance(getattr(container, repo_method)(), expected_type)


@pytest.mark.parametrize(
    ("repo_method", "message"),
    [
        ("checkpoint_repo", "Supabase strategy checkpoint_repo requires supabase_client"),
        ("run_event_repo", "Supabase strategy run_event_repo requires supabase_client"),
        ("file_operation_repo", "Supabase strategy file_operation_repo requires supabase_client"),
        ("summary_repo", "Supabase strategy summary_repo requires supabase_client"),
        ("eval_repo", "Supabase strategy eval_repo requires supabase_client"),
        ("sandbox_monitor_repo", "Supabase strategy sandbox_monitor_repo requires supabase_client"),
    ],
)
def test_storage_container_supabase_repos_require_client(repo_method: str, message: str) -> None:
    container = StorageContainer(strategy="supabase")
    with pytest.raises(RuntimeError, match=message):
        getattr(container, repo_method)()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"strategy": "redis"}, "Unsupported storage strategy: redis. Supported strategies: sqlite, supabase"),
        ({"repo_providers": {"foo_repo": "sqlite"}}, "Unknown repo provider bindings: foo_repo"),
        ({"repo_providers": {"checkpoint_repo": "mysql"}}, "Unsupported provider for checkpoint_repo"),
    ],
)
def test_storage_container_rejects_invalid_configuration(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        StorageContainer(**kwargs)  # type: ignore[arg-type]
