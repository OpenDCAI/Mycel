from types import SimpleNamespace

from backend.bootstrap import storage as runtime_storage_bootstrap


def test_build_runtime_storage_state_uses_shared_supabase_client(monkeypatch):
    calls: list[object] = []
    fake_client = object()
    fake_container = object()

    monkeypatch.setattr(runtime_storage_bootstrap, "create_supabase_client", lambda: fake_client)

    def _build_storage_container(*, supabase_client):
        calls.append(supabase_client)
        return fake_container

    monkeypatch.setattr(runtime_storage_bootstrap, "build_storage_container", _build_storage_container)

    state = runtime_storage_bootstrap.build_runtime_storage_state()

    assert state.supabase_client is fake_client
    assert state.storage_container is fake_container
    assert calls == [fake_client]


def test_attach_runtime_storage_state_sets_app_state(monkeypatch):
    fake_state = SimpleNamespace(supabase_client=object(), storage_container=object())
    app = type("_App", (), {"state": type("_State", (), {})()})()

    monkeypatch.setattr(runtime_storage_bootstrap, "build_runtime_storage_state", lambda: fake_state)

    result = runtime_storage_bootstrap.attach_runtime_storage_state(app)

    assert result is fake_state
    assert app.state._supabase_client is fake_state.supabase_client
    assert app.state._storage_container is fake_state.storage_container
