from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, cast

import jwt
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


class _SchemaRpcSupabaseClient:
    def __init__(self) -> None:
        self.rpc_calls: list[tuple[str, dict[str, object]]] = []
        self.schema_name: str | None = None

    def schema(self, name: str):
        scoped = _SchemaRpcSupabaseClient()
        scoped.rpc_calls = self.rpc_calls
        scoped.schema_name = name
        return scoped

    def rpc(self, name: str, params: dict[str, object]):
        if self.schema_name is None:
            raise AssertionError(f"bare rpc call is not allowed: {name}")
        self.rpc_calls.append((f"{self.schema_name}.{name}", params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=10001))


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
    user_repo=None,
    agent_configs=None,
    invite_codes=None,
    contact_repo=None,
    recipe_repo=None,
) -> AuthService:
    return AuthService(
        users=cast(Any, user_repo or SimpleNamespace()),
        agent_configs=agent_configs,
        supabase_client=supabase_client,
        supabase_auth_client=supabase_auth_client,
        supabase_auth_client_factory=supabase_auth_client_factory,
        invite_codes=invite_codes,
        contact_repo=contact_repo,
        recipe_repo=recipe_repo,
    )


def test_verify_token_uses_local_jwt_secret_without_remote_auth_call(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret-1")
    sb = _FakeSupabaseClient(user_id="user-supabase")
    token = jwt.encode({"sub": "user-local"}, "secret-1", algorithm="HS256")

    payload = _service(supabase_auth_client=sb).verify_token(token)

    assert sb.auth.tokens == []
    assert payload == {"user_id": "user-local"}


def test_verify_token_accepts_supabase_iat_clock_boundary(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret-1")
    token = jwt.encode({"sub": "user-local", "iat": int(time.time()) + 30}, "secret-1", algorithm="HS256")

    payload = _service().verify_token(token)

    assert payload == {"user_id": "user-local"}


def test_verify_token_fails_loudly_when_secret_missing_even_with_auth_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    sb = _FakeSupabaseClient(user_id="user-supabase")

    with pytest.raises(RuntimeError, match="SUPABASE_JWT_SECRET env var required"):
        _service(supabase_auth_client=sb).verify_token("tok-live")
    assert sb.auth.tokens == []


def test_login_uses_dedicated_auth_client_instead_of_storage_client():
    auth_client = _FakeAuthClient()
    user_repo = SimpleNamespace(
        get_by_id=lambda _user_id: SimpleNamespace(display_name="codex", mycel_id=10001, email="codex@example.com", avatar=None),
        list_by_owner_user_id=lambda _user_id: [],
    )

    result = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
        user_repo=user_repo,
    ).login("codex@example.com", "pw-1")

    assert auth_client.auth.calls == [{"email": "codex@example.com", "password": "pw-1"}]
    assert result["token"] == "tok-1"


def test_login_repairs_existing_user_sandbox_recipes(monkeypatch: pytest.MonkeyPatch):
    auth_client = _FakeAuthClient()
    monkeypatch.setattr(
        "backend.web.services.library_service.sandbox_service.available_sandbox_types",
        lambda: [{"name": "daytona_selfhost", "provider": "daytona", "available": True}],
    )
    recipe_rows: dict[tuple[str, str], dict] = {}
    recipe_repo = SimpleNamespace(
        get=lambda owner_user_id, recipe_id: recipe_rows.get((owner_user_id, recipe_id)),
        upsert=lambda **payload: recipe_rows.setdefault(
            (payload["owner_user_id"], payload["recipe_id"]), {"data": payload["data"], **payload}
        ),
    )
    user_repo = SimpleNamespace(
        get_by_id=lambda _user_id: SimpleNamespace(display_name="codex", mycel_id=10001, email="codex@example.com", avatar=None),
        list_by_owner_user_id=lambda _user_id: [],
    )

    _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
        user_repo=user_repo,
        recipe_repo=recipe_repo,
    ).login("codex@example.com", "pw-1")

    assert sorted(recipe_id for (_owner, recipe_id) in recipe_rows) == ["daytona_selfhost:default"]


def test_login_uses_fresh_auth_client_from_factory_per_call():
    created: list[_FactoryBackedAuthClient] = []

    def factory() -> _FactoryBackedAuthClient:
        client = _FactoryBackedAuthClient()
        created.append(client)
        return client

    user_repo = SimpleNamespace(
        get_by_id=lambda _user_id: SimpleNamespace(display_name="codex", mycel_id=10001, email="codex@example.com", avatar=None),
        list_by_owner_user_id=lambda _user_id: [],
    )
    service = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client_factory=factory,
        user_repo=user_repo,
    )

    service.login("codex@example.com", "pw-1")
    service.login("codex@example.com", "pw-2")

    assert len(created) == 2
    assert created[0].calls == [{"email": "codex@example.com", "password": "pw-1"}]
    assert created[1].calls == [{"email": "codex@example.com", "password": "pw-2"}]


def test_verify_token_does_not_use_auth_client_factory(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    created: list[_FactoryBackedAuthClient] = []

    def factory() -> _FactoryBackedAuthClient:
        client = _FactoryBackedAuthClient()
        created.append(client)
        return client

    service = _service(supabase_auth_client_factory=factory)

    with pytest.raises(RuntimeError, match="SUPABASE_JWT_SECRET env var required"):
        service.verify_token("tok-1")
    assert created == []


def test_login_accepts_direct_gotrue_client_without_auth_wrapper():
    auth_client = _DirectAuthClient()
    user_repo = SimpleNamespace(
        get_by_id=lambda _user_id: SimpleNamespace(display_name="codex", mycel_id=10001, email="codex@example.com", avatar=None),
        list_by_owner_user_id=lambda _user_id: [],
    )

    result = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
        user_repo=user_repo,
    ).login("codex@example.com", "pw-1")

    assert auth_client.calls == [{"email": "codex@example.com", "password": "pw-1"}]
    assert result["token"] == "tok-1"


def test_verify_token_does_not_use_direct_gotrue_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    auth_client = _DirectAuthClient()

    with pytest.raises(RuntimeError, match="SUPABASE_JWT_SECRET env var required"):
        _service(supabase_auth_client=auth_client).verify_token("tok-direct")

    assert auth_client.tokens == []


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


def test_complete_register_seeds_user_sandbox_recipes(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret-1")
    monkeypatch.setattr(
        "backend.web.routers.users.process_and_save_avatar",
        lambda _source, user_id: f"avatars/{user_id}.png",
    )
    monkeypatch.setattr(
        "backend.web.services.library_service.sandbox_service.available_sandbox_types",
        lambda: [
            {"name": "local", "provider": "local", "available": True},
            {"name": "daytona_selfhost", "provider": "daytona", "available": True},
        ],
    )
    user_ids = iter(["agent-toad", "agent-morel"])
    config_ids = iter(["cfg-toad", "cfg-morel"])
    monkeypatch.setattr("storage.utils.generate_agent_user_id", lambda: next(user_ids))
    monkeypatch.setattr("storage.utils.generate_agent_config_id", lambda: next(config_ids))

    created_users: dict[str, object] = {}
    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: created_users.get(user_id),
        create=lambda row: created_users.setdefault(row.id, row),
        update=lambda _user_id, **_fields: None,
        list_by_owner_user_id=lambda _user_id: [],
    )
    agent_configs = SimpleNamespace(save_config=lambda _config_id, _payload: None)
    invite_codes = SimpleNamespace(is_valid=lambda code: code == "invite-1", use=lambda _code, _user_id: None)
    contact_repo = SimpleNamespace(upsert=lambda _row: None)
    recipe_rows: dict[str, dict] = {}
    recipe_repo = SimpleNamespace(
        get=lambda owner_user_id, recipe_id: recipe_rows.get((owner_user_id, recipe_id)),
        upsert=lambda **payload: recipe_rows.setdefault(
            (payload["owner_user_id"], payload["recipe_id"]), {"data": payload["data"], **payload}
        ),
    )
    supabase_client = _SchemaRpcSupabaseClient()
    token = jwt.encode({"sub": "owner-1", "email": "fresh@example.com"}, "secret-1", algorithm="HS256")

    _service(
        supabase_client=supabase_client,
        user_repo=user_repo,
        agent_configs=agent_configs,
        invite_codes=invite_codes,
        contact_repo=contact_repo,
        recipe_repo=recipe_repo,
    ).complete_register(token, "invite-1")

    assert supabase_client.rpc_calls == [("identity.next_mycel_id", {})]
    assert sorted(recipe_id for (_owner, recipe_id) in recipe_rows) == ["daytona_selfhost:default", "local:default"]


def test_create_initial_agents_keeps_avatar_column_null_under_file_backed_avatar_shell(monkeypatch: pytest.MonkeyPatch):
    created_users: list[SimpleNamespace] = []
    updates: list[tuple[str, dict[str, object]]] = []
    saved_configs: list[tuple[str, dict[str, object]]] = []
    contact_edges: list[object] = []
    user_ids = iter(["agent-toad", "agent-morel"])
    config_ids = iter(["cfg-toad", "cfg-morel"])

    monkeypatch.setattr("storage.utils.generate_agent_user_id", lambda: next(user_ids))
    monkeypatch.setattr("storage.utils.generate_agent_config_id", lambda: next(config_ids))
    monkeypatch.setattr(
        "backend.web.routers.users.process_and_save_avatar",
        lambda _source, user_id: f"avatars/{user_id}.png",
    )

    user_repo = SimpleNamespace(
        create=lambda row: created_users.append(row),
        update=lambda user_id, **fields: updates.append((user_id, fields)),
    )
    agent_configs = SimpleNamespace(save_config=lambda config_id, payload: saved_configs.append((config_id, payload)))
    contact_repo = SimpleNamespace(upsert=lambda row: contact_edges.append(row))

    result = _service(user_repo=user_repo, agent_configs=agent_configs, contact_repo=contact_repo)._create_initial_agents("owner-1", 123.0)

    assert [row.id for row in created_users] == ["agent-toad", "agent-morel"]
    assert [row.display_name for row in created_users] == ["Toad", "Morel"]
    assert [item[0] for item in saved_configs] == ["cfg-toad", "cfg-morel"]
    assert [item[1]["owner_user_id"] for item in saved_configs] == ["owner-1", "owner-1"]
    assert updates == []
    assert [(row.source_user_id, row.target_user_id, row.kind, row.state) for row in contact_edges] == [
        ("owner-1", "agent-toad", "normal", "active"),
        ("owner-1", "agent-morel", "normal", "active"),
    ]
    assert result == {"id": "agent-toad", "name": "Toad", "type": "agent", "avatar": "avatars/agent-toad.png"}


def test_login_resolves_numeric_mycel_id_via_user_repo():
    auth_client = _FakeAuthClient()
    user_repo = SimpleNamespace(
        get_by_mycel_id=lambda mycel_id: (
            SimpleNamespace(display_name="codex", mycel_id=mycel_id, email="codex@example.com", avatar=None) if mycel_id == 10001 else None
        ),
        get_by_id=lambda _user_id: SimpleNamespace(display_name="codex", mycel_id=10001, email="codex@example.com", avatar=None),
        list_by_owner_user_id=lambda _user_id: [],
    )

    result = _service(
        supabase_client=SimpleNamespace(auth=None),
        supabase_auth_client=auth_client,
        user_repo=user_repo,
    ).login("10001", "pw-1")

    assert auth_client.auth.calls == [{"email": "codex@example.com", "password": "pw-1"}]
    assert result["user"]["mycel_id"] == 10001
