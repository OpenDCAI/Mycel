from __future__ import annotations

from cli.agent import http


def test_chat_http_client_posts_send(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured['raised'] = True
        def json(self) -> dict[str, object]:
            return {'id': 'msg-1'}

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured['base_url'] = base_url
            captured['timeout'] = timeout
            captured['trust_env'] = trust_env
        def __enter__(self):
            return self
        def __exit__(self, *_args) -> None:
            return None
        def post(self, path: str, *, json: dict) -> _Response:
            captured['path'] = path
            captured['json'] = json
            return _Response()

    monkeypatch.setattr(http.httpx, 'Client', _Client)
    client = http.ChatHttpClient(base_url='http://chat-backend')
    payload = client.send('chat-1', 'agent-user-1', 'hello', enforce_caught_up=True)

    assert payload == {'id': 'msg-1'}
    assert captured['path'] == '/api/internal/messaging/chats/chat-1/messages/send'
    assert captured['json']['enforce_caught_up'] is True


def test_identity_http_client_lists_external_users(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured['raised'] = True
        def json(self) -> list[dict[str, object]]:
            return [{'id': 'external-user-1', 'type': 'external'}]

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured['base_url'] = base_url
            captured['timeout'] = timeout
            captured['trust_env'] = trust_env
        def __enter__(self):
            return self
        def __exit__(self, *_args) -> None:
            return None
        def get(self, path: str, *, params: dict | None = None) -> _Response:
            captured['path'] = path
            captured['params'] = params
            return _Response()

    monkeypatch.setattr(http.httpx, 'Client', _Client)
    client = http.IdentityHttpClient(base_url='http://chat-backend')
    payload = client.list_users(user_type='external')

    assert payload == [{'id': 'external-user-1', 'type': 'external'}]
    assert captured['path'] == '/api/internal/identity/users'
    assert captured['params'] == {'type': 'external'}


def test_threads_runtime_http_client_checks_agent_actor(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured['raised'] = True
        def json(self) -> dict[str, object]:
            return {'exists': True}

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured['base_url'] = base_url
            captured['timeout'] = timeout
            captured['trust_env'] = trust_env
        def __enter__(self):
            return self
        def __exit__(self, *_args) -> None:
            return None
        def get(self, path: str, *, params: dict | None = None) -> _Response:
            captured['path'] = path
            captured['params'] = params
            return _Response()

    monkeypatch.setattr(http.httpx, 'Client', _Client)
    client = http.ThreadsRuntimeHttpClient(base_url='http://threads-backend')

    assert client.is_agent_actor_user('agent-user-1') is True
    assert captured['path'] == '/api/internal/identity/agent-actors/agent-user-1/exists'


def test_auth_http_client_posts_login(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

        def json(self) -> dict[str, object]:
            return {"token": "tok-login"}

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured["base_url"] = base_url
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def post(self, path: str, *, json: dict[str, object]) -> _Response:
            captured["path"] = path
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(http.httpx, "Client", _Client)
    client = http.AuthHttpClient(base_url="http://backend")
    payload = client.login("fresh@example.com", "pw-1")

    assert payload == {"token": "tok-login"}
    assert captured["path"] == "/api/auth/login"
    assert captured["json"] == {"identifier": "fresh@example.com", "password": "pw-1"}


def test_panel_http_client_uses_bearer_token(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

        def json(self) -> dict[str, object]:
            return {"items": [{"id": "agent-1"}]}

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured["base_url"] = base_url
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, path: str, *, headers: dict[str, str]) -> _Response:
            captured["path"] = path
            captured["headers"] = headers
            return _Response()

    monkeypatch.setattr(http.httpx, "Client", _Client)
    client = http.PanelHttpClient(base_url="http://backend", auth_token="tok-1")
    payload = client.list_agents()

    assert payload == {"items": [{"id": "agent-1"}]}
    assert captured["path"] == "/api/panel/agents"
    assert captured["headers"] == {"Authorization": "Bearer tok-1"}
