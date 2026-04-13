from __future__ import annotations

from types import SimpleNamespace

from backend.web.core.lifespan import _wire_supabase_runtime


class _FakeSupabaseClient:
    def table(self, table_name: str):
        raise AssertionError(f"table() should not be called in wiring test: {table_name}")

    def schema(self, schema_name: str):
        raise AssertionError(f"schema() should not be called in wiring test: {schema_name}")


def test_supabase_storage_repos_do_not_share_auth_client(monkeypatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    storage_client = _FakeSupabaseClient()
    auth_client = _FakeSupabaseClient()
    app = SimpleNamespace(state=SimpleNamespace())

    _wire_supabase_runtime(app, storage_client=storage_client, auth_client=auth_client)

    assert app.state.thread_repo._client is storage_client
    assert app.state.member_repo._client is storage_client
    assert app.state.auth_service._sb is auth_client
    assert app.state.auth_service._sb is not app.state.thread_repo._client
