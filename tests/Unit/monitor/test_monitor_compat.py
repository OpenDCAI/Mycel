import sqlite3

from backend.web import monitor


def test_list_running_eval_checkpoint_threads_returns_empty_when_eval_tables_absent(tmp_path, monkeypatch):
    db_path = tmp_path / "leon.db"
    sqlite3.connect(db_path).close()
    monkeypatch.setattr(monitor, "DB_PATH", db_path)

    assert monitor._list_running_eval_checkpoint_threads() == []
