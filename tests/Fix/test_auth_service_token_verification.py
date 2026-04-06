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


class _FactoryBackedLoginAuth:
    def __init__(self, owner: _FactoryBackedAuthClient) -> None:
        self._owner = owner

    def sign_in_with_password(self, payload: dict[str, str]):
        self._owner.calls.append(payload)
        return SimpleNamespace(
            user=SimpleNamespace(id="user-1"),
            session=SimpleNamespace(access_token="tok-1"),
        )

    def get_user(self, token: str):
        self._owner.tokens.append(token)
        return SimpleNamespace(user=SimpleNamespace(id="user-1"))


class _FactoryBackedAuthClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.tokens: list[str] = []
        self.auth = _FactoryBackedLoginAuth(self)


class _DirectAuthClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.tokens: list[str] = []

    def sign_in_with_password(self, payload: dict[str, str]):
        self.calls.append(payload)
        return SimpleNamespace(
            user=SimpleNamespace(id="user-1"),
            session=SimpleNamespace(access_token="tok-1"),
        )

    def get_user(self, token: str):
        self.tokens.append(token)
        return SimpleNamespace(user=SimpleNamespace(id="user-1"))

    def sign_up(self, payload: dict[str, str]):
        self.calls.append(payload)
        return SimpleNamespace(user=SimpleNamespace(id="user-1"), session=None)

    def verify_otp(self, payload: dict[str, str]):
        self.calls.append(payload)
        return SimpleNamespace(
            user=SimpleNamespace(id="user-1"),
            session=SimpleNamespace(access_token="temp-token-1"),
        )


def _service(
    *,
    supabase_client=None,
    supabase_auth_client=None,
    supabase_auth_client_factory=None,
    member_repo=None,
    invite_codes=None,
) -> AuthService:
    return AuthService(
        members=member_repo or SimpleNamespace(),
        supabase_client=supabase_client,
        supabase_auth_client=supabase_auth_client,
        supabase_auth_client_factory=supabase_auth_client_factory,
        invite_codes=invite_codes,
    )


def test_verify_token_prefers_supabase_get_user_over_local_jwt_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    sb = _FakeSupabaseClient(user_id="user-supabase")

    payload = _service(supabase_auth_client=sb).verify_token("tok-live")

    assert sb.auth.tokens == ["tok-live"]
    assert payload == {"user_id": "user-supabase"}


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

    result = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
        member_repo=member_repo,
    ).login("codex@example.com", "pw-1")

    assert auth_client.auth.calls == [{"email": "codex@example.com", "password": "pw-1"}]
    assert result["token"] == "tok-1"


def test_login_uses_fresh_auth_client_from_factory_per_call():
    created: list[_FactoryBackedAuthClient] = []

    def factory() -> _FactoryBackedAuthClient:
        client = _FactoryBackedAuthClient()
        created.append(client)
        return client

    member_repo = SimpleNamespace(
        get_by_id=lambda _user_id: SimpleNamespace(name="codex", mycel_id=10001, email="codex@example.com", avatar=None),
        list_by_owner_user_id=lambda _user_id: [],
    )
    service = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client_factory=factory,
        member_repo=member_repo,
    )

    service.login("codex@example.com", "pw-1")
    service.login("codex@example.com", "pw-2")

    assert len(created) == 2
    assert created[0].calls == [{"email": "codex@example.com", "password": "pw-1"}]
    assert created[1].calls == [{"email": "codex@example.com", "password": "pw-2"}]


def test_verify_token_uses_fresh_auth_client_from_factory_per_call(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    created: list[_FactoryBackedAuthClient] = []

    def factory() -> _FactoryBackedAuthClient:
        client = _FactoryBackedAuthClient()
        created.append(client)
        return client

    service = _service(supabase_auth_client_factory=factory)

    assert service.verify_token("tok-1") == {"user_id": "user-1"}
    assert service.verify_token("tok-2") == {"user_id": "user-1"}
    assert len(created) == 2
    assert created[0].tokens == ["tok-1"]
    assert created[1].tokens == ["tok-2"]


def test_login_accepts_direct_gotrue_client_without_auth_wrapper():
    auth_client = _DirectAuthClient()
    member_repo = SimpleNamespace(
        get_by_id=lambda _user_id: SimpleNamespace(name="codex", mycel_id=10001, email="codex@example.com", avatar=None),
        list_by_owner_user_id=lambda _user_id: [],
    )

    result = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
        member_repo=member_repo,
    ).login("codex@example.com", "pw-1")

    assert auth_client.calls == [{"email": "codex@example.com", "password": "pw-1"}]
    assert result["token"] == "tok-1"


def test_verify_token_accepts_direct_gotrue_client_without_auth_wrapper(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    auth_client = _DirectAuthClient()

    payload = _service(supabase_auth_client=auth_client).verify_token("tok-direct")

    assert auth_client.tokens == ["tok-direct"]
    assert payload == {"user_id": "user-1"}


def test_send_otp_accepts_direct_gotrue_client_without_auth_wrapper():
    auth_client = _DirectAuthClient()
    invite_codes = SimpleNamespace(is_valid=lambda code: code == "invite-1")

    _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
        invite_codes=invite_codes,
    ).send_otp("fresh@example.com", "pw-1", "invite-1")

    assert auth_client.calls == [{"email": "fresh@example.com", "password": "pw-1"}]


def test_verify_register_otp_accepts_direct_gotrue_client_without_auth_wrapper():
    auth_client = _DirectAuthClient()

    result = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
    ).verify_register_otp("fresh@example.com", "123456")

    assert auth_client.calls == [{"email": "fresh@example.com", "token": "123456", "type": "signup"}]
    assert result == {"temp_token": "temp-token-1"}
