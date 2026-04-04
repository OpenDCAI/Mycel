from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.services.auth_service import AuthService


class _FakeSupabaseAuth:
    def __init__(self, user_id: str = "user-1") -> None:
        self.user_id = user_id
        self.tokens: list[str] = []

    def get_user(self, token: str):
        self.tokens.append(token)
        return SimpleNamespace(user=SimpleNamespace(id=self.user_id))


class _FakeSupabaseClient:
    def __init__(self, user_id: str = "user-1") -> None:
        self.auth = _FakeSupabaseAuth(user_id=user_id)


class _FakeLoginAuth:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def sign_in_with_password(self, payload: dict[str, str]):
        self.calls.append(payload)
        return SimpleNamespace(
            user=SimpleNamespace(id="user-1"),
            session=SimpleNamespace(access_token="tok-1"),
        )


class _FakeAuthClient:
    def __init__(self) -> None:
        self.auth = _FakeLoginAuth()


def _service(*, supabase_client=None, supabase_auth_client=None, member_repo=None, entity_repo=None) -> AuthService:
    return AuthService(
        members=member_repo or SimpleNamespace(),
        accounts=SimpleNamespace(),
        entities=entity_repo or SimpleNamespace(),
        supabase_client=supabase_client,
        supabase_auth_client=supabase_auth_client,
    )


def test_verify_token_prefers_supabase_get_user_over_local_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    sb = _FakeSupabaseClient(user_id="user-supabase")

    payload = _service(supabase_auth_client=sb).verify_token("tok-live")

    assert sb.auth.tokens == ["tok-live"]
    assert payload == {"user_id": "user-supabase", "entity_id": None}


def test_verify_token_without_supabase_client_still_fails_loudly_when_secret_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="SUPABASE_JWT_SECRET env var required"):
        _service().verify_token("tok-live")


def test_login_uses_dedicated_auth_client_instead_of_storage_client():
    auth_client = _FakeAuthClient()
    member_repo = SimpleNamespace(
        get_by_id=lambda _user_id: SimpleNamespace(name="codex", mycel_id=10001, email="codex@example.com", avatar=None),
        list_by_owner_user_id=lambda _user_id: [],
    )
    entity_repo = SimpleNamespace(get_by_member_id=lambda _user_id: [SimpleNamespace(id="user-1-1", type="human")])

    result = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
        member_repo=member_repo,
        entity_repo=entity_repo,
    ).login("codex@example.com", "pw-1")

    assert auth_client.auth.calls == [{"email": "codex@example.com", "password": "pw-1"}]
    assert result["token"] == "tok-1"
