import pytest
from supabase_auth._sync.gotrue_client import SyncGoTrueClient

from backend import supabase_runtime
from backend.web.core.supabase_factory import create_supabase_auth_client, create_supabase_client


def test_web_supabase_factory_is_compat_shell():
    assert create_supabase_client is supabase_runtime.create_supabase_client
    assert create_supabase_auth_client is supabase_runtime.create_supabase_auth_client


def test_create_supabase_auth_client_prefers_auth_url(monkeypatch):
    monkeypatch.setenv("SUPABASE_PUBLIC_URL", "http://storage.example.test")
    monkeypatch.setenv("SUPABASE_AUTH_URL", "http://auth.example.test")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    client = create_supabase_auth_client()

    assert isinstance(client, SyncGoTrueClient)
    assert client._url == "http://auth.example.test"


def test_create_supabase_auth_client_uses_direct_gotrue_for_auth_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_PUBLIC_URL", raising=False)
    monkeypatch.setenv("SUPABASE_AUTH_URL", "http://auth.example.test")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    client = create_supabase_auth_client()

    assert isinstance(client, SyncGoTrueClient)
    assert client._url == "http://auth.example.test"


def test_create_supabase_client_requires_runtime_schema(monkeypatch):
    monkeypatch.setenv("SUPABASE_INTERNAL_URL", "http://storage.example.test")
    monkeypatch.setenv("LEON_SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.delenv("LEON_DB_SCHEMA", raising=False)

    with pytest.raises(RuntimeError, match="LEON_DB_SCHEMA is required"):
        create_supabase_client()


def test_create_supabase_client_uses_runtime_schema(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_client(url, key, options=None):
        captured["options"] = options
        return object()

    monkeypatch.setenv("SUPABASE_INTERNAL_URL", "http://storage.example.test")
    monkeypatch.setenv("LEON_SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("LEON_DB_SCHEMA", "agent")
    monkeypatch.setattr("backend.supabase_runtime.create_client", fake_create_client)

    create_supabase_client()

    assert getattr(captured["options"], "schema", None) == "agent"
