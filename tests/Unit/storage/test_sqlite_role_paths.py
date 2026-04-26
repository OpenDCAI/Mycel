from __future__ import annotations

from pathlib import Path

import pytest

from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


@pytest.mark.parametrize(
    ("role", "env_var"),
    [
        (SQLiteDBRole.MAIN, "LEON_DB_PATH"),
        (SQLiteDBRole.SANDBOX, "LEON_SANDBOX_DB_PATH"),
        (SQLiteDBRole.QUEUE, "LEON_QUEUE_DB_PATH"),
    ],
)
def test_sqlite_role_path_requires_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
    role: SQLiteDBRole,
    env_var: str,
) -> None:
    monkeypatch.delenv("LEON_DB_PATH", raising=False)
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)
    monkeypatch.delenv("LEON_QUEUE_DB_PATH", raising=False)

    with pytest.raises(RuntimeError, match=env_var):
        resolve_role_db_path(role)


def test_queue_role_does_not_derive_from_main_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "main.db"))
    monkeypatch.delenv("LEON_QUEUE_DB_PATH", raising=False)

    with pytest.raises(RuntimeError, match="LEON_QUEUE_DB_PATH"):
        resolve_role_db_path(SQLiteDBRole.QUEUE)


@pytest.mark.parametrize(
    ("role", "env_var", "file_name"),
    [
        (SQLiteDBRole.MAIN, "LEON_DB_PATH", "main.db"),
        (SQLiteDBRole.SANDBOX, "LEON_SANDBOX_DB_PATH", "sandbox.db"),
        (SQLiteDBRole.QUEUE, "LEON_QUEUE_DB_PATH", "queue.db"),
    ],
)
def test_sqlite_role_path_uses_matching_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    role: SQLiteDBRole,
    env_var: str,
    file_name: str,
) -> None:
    expected = tmp_path / file_name
    monkeypatch.setenv(env_var, str(expected))

    assert resolve_role_db_path(role) == expected


def test_explicit_sqlite_db_path_bypasses_role_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LEON_QUEUE_DB_PATH", raising=False)

    explicit = tmp_path / "explicit.db"

    assert resolve_role_db_path(SQLiteDBRole.QUEUE, explicit) == explicit
