from __future__ import annotations

from backend.chat import identity_client


def test_http_identity_client_posts_create_external_user(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured['raised'] = True
        def json(self) -> dict[str, object]:
            return {'id': 'external-user-1', 'type': 'external', 'display_name': 'Codex External'}

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

    monkeypatch.setattr(identity_client.httpx, 'Client', _Client)
    client = identity_client.HttpIdentityClient(base_url='http://chat-backend')
    payload = client.create_external_user(user_id='external-user-1', display_name='Codex External')

    assert payload['id'] == 'external-user-1'
    assert captured == {
        'base_url': 'http://chat-backend',
        'timeout': 10.0,
        'trust_env': False,
        'path': '/api/internal/identity/users/external',
        'json': {'user_id': 'external-user-1', 'display_name': 'Codex External'},
        'raised': True,
    }


def test_http_identity_client_lists_users_by_type(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured['raised'] = True
        def json(self) -> list[dict[str, object]]:
            return [{'id': 'external-user-1', 'type': 'external', 'display_name': 'Codex External'}]

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

    monkeypatch.setattr(identity_client.httpx, 'Client', _Client)
    client = identity_client.HttpIdentityClient(base_url='http://chat-backend')
    payload = client.list_users(user_type='external')

    assert payload == [{'id': 'external-user-1', 'type': 'external', 'display_name': 'Codex External'}]
    assert captured == {
        'base_url': 'http://chat-backend',
        'timeout': 10.0,
        'trust_env': False,
        'path': '/api/internal/identity/users',
        'params': {'type': 'external'},
        'raised': True,
    }
