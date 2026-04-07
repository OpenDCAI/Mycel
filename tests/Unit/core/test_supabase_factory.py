from supabase_auth._sync.gotrue_client import SyncGoTrueClient

from backend.web.core.supabase_factory import create_messaging_supabase_client, create_supabase_auth_client


def test_create_supabase_auth_client_prefers_auth_url(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://storage.example.test")
    monkeypatch.setenv("SUPABASE_AUTH_URL", "http://auth.example.test")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    client = create_supabase_auth_client()

    assert isinstance(client, SyncGoTrueClient)
    assert client._url == "http://auth.example.test"


def test_create_supabase_auth_client_uses_direct_gotrue_for_auth_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_AUTH_URL", "http://auth.example.test")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    client = create_supabase_auth_client()

    assert isinstance(client, SyncGoTrueClient)
    assert client._url == "http://auth.example.test"


def test_create_messaging_supabase_client_uses_service_role_key(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_client(url, key, options=None):
        captured["url"] = url
        captured["key"] = key
        captured["options"] = options
        return object()

    monkeypatch.setenv("SUPABASE_URL", "http://storage.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setattr("backend.web.core.supabase_factory.create_client", fake_create_client)

    create_messaging_supabase_client()

    assert captured["url"] == "http://storage.example.test"
    assert captured["key"] == "service-role-key"


def test_create_messaging_supabase_client_forces_public_schema(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_client(url, key, options=None):
        captured["options"] = options
        return object()

    monkeypatch.setenv("SUPABASE_URL", "http://storage.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setattr("backend.web.core.supabase_factory.create_client", fake_create_client)

    create_messaging_supabase_client()

    assert getattr(captured["options"], "schema", None) == "public"
