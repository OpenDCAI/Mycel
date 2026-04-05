import sqlite3
from pathlib import Path

import pytest

from backend.web.utils import helpers
from storage.providers.sqlite.thread_config_repo import SQLiteThreadConfigRepo
from storage.providers.supabase.thread_config_repo import SupabaseThreadConfigRepo


def test_migrate_thread_metadata_table(tmp_path):
    db_path = tmp_path / "leon.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE thread_metadata (thread_id TEXT PRIMARY KEY, sandbox_type TEXT NOT NULL, cwd TEXT, model TEXT)"
        )
        conn.execute(
            "INSERT INTO thread_metadata (thread_id, sandbox_type, cwd, model) VALUES (?, ?, ?, ?)",
            ("t-1", "local", "/tmp/ws", "m-1"),
        )
        conn.commit()

    repo = SQLiteThreadConfigRepo(db_path)
    try:
        assert repo.lookup_metadata("t-1") == ("local", "/tmp/ws")
        assert repo.lookup_model("t-1") == "m-1"
    finally:
        repo.close()

    with sqlite3.connect(str(db_path)) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "thread_config" in tables
        assert "thread_metadata" not in tables


def test_save_and_lookup_thread_config(tmp_path):
    db_path = tmp_path / "leon.db"
    repo = SQLiteThreadConfigRepo(db_path)
    try:
        repo.save_metadata("t-2", "docker", "/workspace")
        repo.save_model("t-2", "anthropic/claude-sonnet-4.6")
        assert repo.lookup_metadata("t-2") == ("docker", "/workspace")
        assert repo.lookup_model("t-2") == "anthropic/claude-sonnet-4.6"
        repo.update_fields("t-2", queue_mode="followup", observation_provider="langfuse")
        cfg = repo.lookup_config("t-2")
        assert cfg is not None
        assert cfg["queue_mode"] == "followup"
        assert cfg["observation_provider"] == "langfuse"
    finally:
        repo.close()


def test_helpers_compatibility_api(tmp_path, monkeypatch):
    db_path = tmp_path / "leon.db"
    monkeypatch.setattr(helpers, "DB_PATH", Path(db_path))

    helpers.init_thread_config("t-3", "local", "/tmp/p")
    helpers.save_thread_model("t-3", "m-3")

    config = helpers.load_thread_config("t-3")
    assert config is not None
    assert (config.sandbox_type, config.cwd) == ("local", "/tmp/p")
    assert helpers.lookup_thread_model("t-3") == "m-3"
    helpers.save_thread_config("t-3", observation_provider="langsmith")
    config2 = helpers.load_thread_config("t-3")
    assert config2 is not None
    assert config2.observation_provider == "langsmith"


from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_thread_config_repo_save_and_lookup():
    tables: dict[str, list[dict]] = {"thread_config": []}
    repo = SupabaseThreadConfigRepo(client=FakeSupabaseClient(tables=tables))

    repo.save_metadata("t-1", "docker", "/workspace")
    repo.save_model("t-1", "anthropic/claude-sonnet-4.6")

    assert repo.lookup_metadata("t-1") == ("docker", "/workspace")
    assert repo.lookup_model("t-1") == "anthropic/claude-sonnet-4.6"

    repo.save_model("t-2", "openai/gpt-5")
    assert repo.lookup_metadata("t-2") == ("local", None)
    assert repo.lookup_model("t-2") == "openai/gpt-5"
    repo.update_fields("t-1", queue_mode="followup", observation_provider="langfuse")
    cfg = repo.lookup_config("t-1")
    assert cfg is not None
    assert cfg["queue_mode"] == "followup"
    assert cfg["observation_provider"] == "langfuse"


def test_supabase_thread_config_repo_delete():
    tables: dict[str, list[dict]] = {"thread_config": []}
    repo = SupabaseThreadConfigRepo(client=FakeSupabaseClient(tables=tables))
    repo.save_metadata("t-1", "docker", "/workspace")
    repo.save_metadata("t-2", "local", None)

    repo.delete_thread_config("t-1")
    assert repo.lookup_metadata("t-1") is None
    assert repo.lookup_metadata("t-2") == ("local", None)


def test_sqlite_thread_config_repo_delete(tmp_path):
    db_path = tmp_path / "leon.db"
    repo = SQLiteThreadConfigRepo(db_path)
    try:
        repo.save_metadata("t-1", "docker", "/workspace")
        repo.save_metadata("t-2", "local", None)
        repo.delete_thread_config("t-1")
        assert repo.lookup_metadata("t-1") is None
        assert repo.lookup_metadata("t-2") == ("local", None)
    finally:
        repo.close()


def test_supabase_thread_config_repo_requires_compatible_client():
    with pytest.raises(RuntimeError, match="table\\(name\\)"):
        SupabaseThreadConfigRepo(client=object())
