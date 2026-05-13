import pytest

import core.runtime.langgraph_checkpoint_store as checkpoint_store
from core.runtime.langgraph_checkpoint_store import agent_checkpoint_conn_string


def test_agent_checkpoint_conn_string_adds_agent_search_path() -> None:
    conn = agent_checkpoint_conn_string("postgresql://user:pass@db.example/postgres")

    assert conn == "postgresql://user:pass@db.example/postgres?options=-csearch_path%3Dagent"


def test_agent_checkpoint_conn_string_preserves_existing_query_params() -> None:
    conn = agent_checkpoint_conn_string("postgresql://user:pass@db.example/postgres?sslmode=require")

    assert conn == "postgresql://user:pass@db.example/postgres?sslmode=require&options=-csearch_path%3Dagent"


def test_agent_checkpoint_conn_string_merges_existing_libpq_options() -> None:
    conn = agent_checkpoint_conn_string("postgresql://user:pass@db.example/postgres?options=-cstatement_timeout%3D5000")

    assert conn == "postgresql://user:pass@db.example/postgres?options=-cstatement_timeout%3D5000%20-csearch_path%3Dagent"


@pytest.mark.asyncio
async def test_agent_checkpoint_saver_sets_agent_search_path_on_open_connection(monkeypatch) -> None:
    opened: dict[str, object] = {}

    class _FakeConnection:
        def __init__(self) -> None:
            self.executed: list[str] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info):
            return None

        async def execute(self, sql: str):
            self.executed.append(sql)

    class _FakeAsyncConnection:
        @staticmethod
        async def connect(conn_string: str, **kwargs):
            conn = _FakeConnection()
            opened["conn"] = conn
            opened["conn_string"] = conn_string
            opened["kwargs"] = kwargs
            return conn

    class _FakeSaver:
        def __init__(self, *, conn, serde=None):
            self.conn = conn
            self.serde = serde

    monkeypatch.setattr(checkpoint_store, "AsyncConnection", _FakeAsyncConnection)
    monkeypatch.setattr(checkpoint_store, "AsyncPostgresSaver", _FakeSaver)

    async with checkpoint_store.agent_checkpoint_saver_from_conn_string("postgresql://user:pass@db.example/postgres") as saver:
        assert saver.conn is opened["conn"]

    assert opened["conn_string"] == "postgresql://user:pass@db.example/postgres?options=-csearch_path%3Dagent"
    assert opened["kwargs"]["autocommit"] is True
    assert opened["conn"].executed == ["SET search_path TO agent"]
