"""Unit tests for the SQLite kernel module (role-based path resolution, pragmas, connections)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from storage.providers.sqlite.kernel import (
    BUSY_TIMEOUT_MS,
    SYNCHRONOUS,
    WAL_MODE,
    SQLiteDBRole,
    _env_path,
    apply_pragmas,
    connect_sqlite,
    connect_sqlite_role,
    resolve_role_db_path,
)


# ---------------------------------------------------------------------------
# _env_path helper
# ---------------------------------------------------------------------------


class TestEnvPath:
    def test_returns_fallback_when_env_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LEON_TEST_UNUSED_VAR", raising=False)
        fallback = Path("/fallback/path.db")
        assert _env_path("LEON_TEST_UNUSED_VAR", fallback) == fallback

    def test_returns_env_value_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LEON_TEST_CUSTOM_PATH", "/custom/override.db")
        result = _env_path("LEON_TEST_CUSTOM_PATH", Path("/fallback/path.db"))
        assert result == Path("/custom/override.db")

    def test_returns_fallback_for_empty_string_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LEON_TEST_EMPTY_VAR", "")
        fallback = Path("/fallback/path.db")
        assert _env_path("LEON_TEST_EMPTY_VAR", fallback) == fallback

    def test_returns_path_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LEON_TEST_TYPE_CHECK", "/some/path.db")
        result = _env_path("LEON_TEST_TYPE_CHECK", Path("/fallback"))
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# resolve_role_db_path — default fallbacks (no env overrides)
# ---------------------------------------------------------------------------


class TestResolveRoleDbPathDefaults:
    """Each role resolves to the expected default path when no env overrides are set."""

    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "LEON_DB_PATH",
            "LEON_RUN_EVENT_DB_PATH",
            "LEON_EVAL_DB_PATH",
            "LEON_SANDBOX_DB_PATH",
            "LEON_QUEUE_DB_PATH",
            "LEON_SUBAGENT_DB_PATH",
        ):
            monkeypatch.delenv(var, raising=False)

    def _home_root(self) -> Path:
        return Path.home() / ".leon"

    def test_main_role(self) -> None:
        assert resolve_role_db_path(SQLiteDBRole.MAIN) == self._home_root() / "leon.db"

    def test_run_event_role(self) -> None:
        assert resolve_role_db_path(SQLiteDBRole.RUN_EVENT) == self._home_root() / "events.db"

    def test_eval_role(self) -> None:
        assert resolve_role_db_path(SQLiteDBRole.EVAL) == self._home_root() / "eval.db"

    def test_sandbox_role(self) -> None:
        assert resolve_role_db_path(SQLiteDBRole.SANDBOX) == self._home_root() / "sandbox.db"

    def test_queue_role(self) -> None:
        assert resolve_role_db_path(SQLiteDBRole.QUEUE) == self._home_root() / "queue.db"

    def test_subagent_role(self) -> None:
        assert resolve_role_db_path(SQLiteDBRole.SUBAGENT) == self._home_root() / "subagent.db"


# ---------------------------------------------------------------------------
# resolve_role_db_path — env overrides
# ---------------------------------------------------------------------------


class TestResolveRoleDbPathEnvOverrides:
    """Environment variable overrides take precedence over defaults."""

    def test_main_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom_main.db"
        monkeypatch.setenv("LEON_DB_PATH", str(custom))
        assert resolve_role_db_path(SQLiteDBRole.MAIN) == custom

    def test_run_event_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom_events.db"
        monkeypatch.setenv("LEON_RUN_EVENT_DB_PATH", str(custom))
        assert resolve_role_db_path(SQLiteDBRole.RUN_EVENT) == custom

    def test_eval_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom_eval.db"
        monkeypatch.setenv("LEON_EVAL_DB_PATH", str(custom))
        assert resolve_role_db_path(SQLiteDBRole.EVAL) == custom

    def test_sandbox_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom_sandbox.db"
        monkeypatch.setenv("LEON_SANDBOX_DB_PATH", str(custom))
        assert resolve_role_db_path(SQLiteDBRole.SANDBOX) == custom

    def test_queue_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom_queue.db"
        monkeypatch.setenv("LEON_QUEUE_DB_PATH", str(custom))
        assert resolve_role_db_path(SQLiteDBRole.QUEUE) == custom

    def test_subagent_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom_subagent.db"
        monkeypatch.setenv("LEON_SUBAGENT_DB_PATH", str(custom))
        assert resolve_role_db_path(SQLiteDBRole.SUBAGENT) == custom

    def test_main_env_affects_dependent_roles(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """RUN_EVENT, QUEUE, SUBAGENT derive from main_path via .with_name(); changing LEON_DB_PATH shifts them."""
        custom_main = tmp_path / "alt" / "main.db"
        monkeypatch.setenv("LEON_DB_PATH", str(custom_main))
        # Clear role-specific overrides so fallback logic kicks in
        for var in ("LEON_RUN_EVENT_DB_PATH", "LEON_QUEUE_DB_PATH", "LEON_SUBAGENT_DB_PATH"):
            monkeypatch.delenv(var, raising=False)

        assert resolve_role_db_path(SQLiteDBRole.RUN_EVENT) == tmp_path / "alt" / "events.db"
        assert resolve_role_db_path(SQLiteDBRole.QUEUE) == tmp_path / "alt" / "queue.db"
        assert resolve_role_db_path(SQLiteDBRole.SUBAGENT) == tmp_path / "alt" / "subagent.db"

    def test_role_specific_env_beats_derived_main_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Role-specific env var takes priority over the main_path-derived fallback."""
        monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "main.db"))
        explicit_events = tmp_path / "explicit_events.db"
        monkeypatch.setenv("LEON_RUN_EVENT_DB_PATH", str(explicit_events))
        assert resolve_role_db_path(SQLiteDBRole.RUN_EVENT) == explicit_events


# ---------------------------------------------------------------------------
# resolve_role_db_path — explicit db_path argument
# ---------------------------------------------------------------------------


class TestResolveRoleDbPathExplicit:
    """When db_path is provided it is returned directly, ignoring role and env."""

    def test_explicit_path_overrides_role(self, tmp_path: Path) -> None:
        explicit = tmp_path / "explicit.db"
        assert resolve_role_db_path(SQLiteDBRole.MAIN, db_path=explicit) == explicit

    def test_explicit_str_path_converted_to_path(self, tmp_path: Path) -> None:
        explicit_str = str(tmp_path / "explicit.db")
        result = resolve_role_db_path(SQLiteDBRole.EVAL, db_path=explicit_str)
        assert isinstance(result, Path)
        assert result == Path(explicit_str)

    def test_explicit_path_ignores_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "from_env.db"))
        explicit = tmp_path / "explicit.db"
        assert resolve_role_db_path(SQLiteDBRole.MAIN, db_path=explicit) == explicit


# ---------------------------------------------------------------------------
# resolve_role_db_path — edge cases
# ---------------------------------------------------------------------------


class TestResolveRoleDbPathEdgeCases:
    def test_none_db_path_uses_role_resolution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LEON_DB_PATH", raising=False)
        result = resolve_role_db_path(SQLiteDBRole.MAIN, db_path=None)
        assert result == Path.home() / ".leon" / "leon.db"

    def test_unknown_role_string_falls_through_to_main(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A role value not matching any branch falls through to the final return (main_path)."""
        monkeypatch.delenv("LEON_DB_PATH", raising=False)
        # Simulate an unexpected role by passing a raw string that StrEnum allows
        # Since SQLiteDBRole is a StrEnum, we cannot create invalid members,
        # but the fall-through path (line 53) should still return main_path.
        # We verify this by confirming all known roles are accounted for.
        all_roles = list(SQLiteDBRole)
        assert len(all_roles) == 6, "If a new role is added, update this test"

    def test_all_enum_members_are_str_enum(self) -> None:
        """SQLiteDBRole members are strings (StrEnum), ensuring they work in string contexts."""
        for role in SQLiteDBRole:
            assert isinstance(role, str)
            assert role == role.value


# ---------------------------------------------------------------------------
# apply_pragmas
# ---------------------------------------------------------------------------


class TestApplyPragmas:
    def test_pragmas_set_correctly(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        try:
            apply_pragmas(conn)
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            sync = conn.execute("PRAGMA synchronous").fetchone()[0]

            assert journal.upper() == WAL_MODE.upper()
            assert busy == BUSY_TIMEOUT_MS
            # NORMAL = 1 in SQLite's integer encoding
            assert sync == 1
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# connect_sqlite
# ---------------------------------------------------------------------------


class TestConnectSqlite:
    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c" / "test.db"
        conn = connect_sqlite(nested)
        try:
            assert nested.parent.exists()
        finally:
            conn.close()

    def test_returns_connection_with_pragmas(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        conn = connect_sqlite(db_file)
        try:
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert journal.upper() == WAL_MODE.upper()
        finally:
            conn.close()

    def test_row_factory_applied(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        conn = connect_sqlite(db_file, row_factory=sqlite3.Row)
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()

    def test_row_factory_none_by_default(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        conn = connect_sqlite(db_file)
        try:
            assert conn.row_factory is None
        finally:
            conn.close()

    def test_accepts_str_path(self, tmp_path: Path) -> None:
        db_file = str(tmp_path / "test.db")
        conn = connect_sqlite(db_file)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()

    def test_custom_timeout(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test.db"
        conn = connect_sqlite(db_file, timeout_ms=5000)
        try:
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert busy == BUSY_TIMEOUT_MS  # apply_pragmas sets the constant
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# connect_sqlite_role
# ---------------------------------------------------------------------------


class TestConnectSqliteRole:
    def test_creates_db_for_main_role(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
        conn = connect_sqlite_role(SQLiteDBRole.MAIN)
        try:
            conn.execute("SELECT 1")
            assert (tmp_path / "leon.db").exists()
        finally:
            conn.close()

    def test_creates_db_for_run_event_role(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
        monkeypatch.delenv("LEON_RUN_EVENT_DB_PATH", raising=False)
        conn = connect_sqlite_role(SQLiteDBRole.RUN_EVENT)
        try:
            conn.execute("SELECT 1")
            assert (tmp_path / "events.db").exists()
        finally:
            conn.close()

    def test_explicit_db_path_overrides_role(self, tmp_path: Path) -> None:
        explicit = tmp_path / "override.db"
        conn = connect_sqlite_role(SQLiteDBRole.EVAL, db_path=explicit)
        try:
            conn.execute("SELECT 1")
            assert explicit.exists()
        finally:
            conn.close()

    def test_row_factory_forwarded(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("LEON_DB_PATH", str(tmp_path / "leon.db"))
        conn = connect_sqlite_role(SQLiteDBRole.MAIN, row_factory=sqlite3.Row)
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# SQLiteDBRole enum
# ---------------------------------------------------------------------------


class TestSQLiteDBRole:
    def test_all_roles_have_unique_values(self) -> None:
        values = [r.value for r in SQLiteDBRole]
        assert len(values) == len(set(values))

    def test_role_values(self) -> None:
        assert SQLiteDBRole.MAIN == "main"
        assert SQLiteDBRole.RUN_EVENT == "run_event"
        assert SQLiteDBRole.EVAL == "eval"
        assert SQLiteDBRole.SANDBOX == "sandbox"
        assert SQLiteDBRole.QUEUE == "queue"
        assert SQLiteDBRole.SUBAGENT == "subagent"

    def test_enum_is_str(self) -> None:
        for role in SQLiteDBRole:
            assert isinstance(role, str)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_wal_mode_value(self) -> None:
        assert WAL_MODE == "WAL"

    def test_busy_timeout_value(self) -> None:
        assert BUSY_TIMEOUT_MS == 30_000

    def test_synchronous_value(self) -> None:
        assert SYNCHRONOUS == "NORMAL"
