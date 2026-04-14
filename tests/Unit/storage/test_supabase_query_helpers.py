import httpx
import pytest
from postgrest import SyncPostgrestClient

from storage.providers.supabase import _query as q


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self.in_calls: list[tuple[str, list[str]]] = []

    def in_(self, column: str, values: list[str]):
        if len(values) > q.IN_FILTER_CHUNK_SIZE:
            raise AssertionError("query was not chunked")
        self.in_calls.append((column, list(values)))
        return self

    def execute(self):
        column, values = self.in_calls[-1]
        return _Response([row for row in self._rows if row.get(column) in values])


class _SupabaseStyleClient:
    def __init__(self, postgrest_client: SyncPostgrestClient):
        self.postgrest = postgrest_client

    def schema(self, schema: str):
        return self.postgrest.schema(schema)

    def table(self, table: str):
        return self.postgrest.table(table)


def test_rows_in_chunks_splits_large_in_filters() -> None:
    rows = [{"id": f"item-{index}", "value": index} for index in range(175)]
    queries: list[_Query] = []

    def make_query() -> _Query:
        query = _Query(rows)
        queries.append(query)
        return query

    result = q.rows_in_chunks(make_query, "id", [f"item-{index}" for index in range(175)], "test repo", "list")

    assert len(result) == 175
    assert [len(query.in_calls[0][1]) for query in queries] == [80, 80, 15]


def test_rows_in_chunks_raises_for_invalid_payload() -> None:
    class BadQuery:
        def in_(self, _column: str, _values: list[str]):
            return self

        def execute(self):
            return _Response({"not": "a list"})

    with pytest.raises(RuntimeError, match="expected list payload"):
        q.rows_in_chunks(BadQuery, "id", ["item-1"], "test repo", "bad")


def test_execute_in_chunks_splits_large_in_filters() -> None:
    queries: list[_Query] = []

    def make_query() -> _Query:
        query = _Query([])
        queries.append(query)
        return query

    q.execute_in_chunks(make_query, "id", [f"item-{index}" for index in range(175)], "test repo", "delete")

    assert [len(query.in_calls[0][1]) for query in queries] == [80, 80, 15]


def test_schema_table_preserves_injected_postgrest_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1")

    session = httpx.Client(trust_env=False)
    client = _SupabaseStyleClient(
        SyncPostgrestClient(
            "http://example.test",
            schema="public",
            http_client=session,
        )
    )

    query = q.schema_table(client, "agent", "threads", "test repo")

    assert query.session is session
    assert str(query.path) == "http://example.test/threads"
    assert query.headers["accept-profile"] == "agent"
