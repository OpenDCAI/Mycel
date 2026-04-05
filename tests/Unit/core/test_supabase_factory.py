from supabase_auth import SyncGoTrueClient

from backend.web.core.supabase_factory import create_supabase_auth_client


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
