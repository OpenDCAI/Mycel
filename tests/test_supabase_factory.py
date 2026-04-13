from __future__ import annotations

import pytest

from backend.web.core import supabase_factory


def _set_required_supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_INTERNAL_URL", "https://supabase.example.test")
    monkeypatch.setenv("LEON_SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


def test_create_supabase_client_requires_explicit_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_supabase_env(monkeypatch)
    monkeypatch.delenv("LEON_DB_SCHEMA", raising=False)

    with pytest.raises(RuntimeError, match="LEON_DB_SCHEMA"):
        supabase_factory.create_supabase_client()


def test_create_supabase_client_rejects_unknown_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_supabase_env(monkeypatch)
    monkeypatch.setenv("LEON_DB_SCHEMA", "identity")

    with pytest.raises(RuntimeError, match="Unsupported LEON_DB_SCHEMA"):
        supabase_factory.create_supabase_client()


def test_create_supabase_client_passes_explicit_staging_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_supabase_env(monkeypatch)
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    captured: dict[str, object] = {}

    def fake_create_client(url: str, key: str, *, options: object):
        captured["url"] = url
        captured["key"] = key
        captured["schema"] = getattr(options, "schema", None)
        return "client"

    monkeypatch.setattr(supabase_factory, "create_client", fake_create_client)

    assert supabase_factory.create_supabase_client() == "client"
    assert captured == {
        "url": "https://supabase.example.test",
        "key": "service-role-key",
        "schema": "staging",
    }
