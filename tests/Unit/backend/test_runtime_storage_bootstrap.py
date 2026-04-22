from types import SimpleNamespace

from backend.bootstrap import storage as runtime_storage_bootstrap


def test_build_runtime_storage_state_uses_shared_supabase_client(monkeypatch):
    calls: list[object] = []
    fake_client = object()
    fake_container = SimpleNamespace()
    fake_recipe_repo = object()

    monkeypatch.setattr(runtime_storage_bootstrap, "create_supabase_client", lambda: fake_client)

    def _build_storage_container(*, supabase_client):
        calls.append(supabase_client)
        return fake_container

    monkeypatch.setattr(runtime_storage_bootstrap, "build_storage_container", _build_storage_container)
    fake_container.recipe_repo = lambda: fake_recipe_repo

    state = runtime_storage_bootstrap.build_runtime_storage_state()

    assert state.supabase_client is fake_client
    assert state.storage_container is fake_container
    assert state.recipe_repo is fake_recipe_repo
    assert calls == [fake_client]


def test_attach_runtime_storage_state_returns_bundle_without_loose_state_mirrors(monkeypatch):
    fake_state = SimpleNamespace(supabase_client=object(), storage_container=object(), recipe_repo=object())
    app = type("_App", (), {"state": type("_State", (), {})()})()

    monkeypatch.setattr(runtime_storage_bootstrap, "build_runtime_storage_state", lambda: fake_state)

    result = runtime_storage_bootstrap.attach_runtime_storage_state(app)

    assert result is fake_state
    assert not hasattr(app.state, "_supabase_client")
    assert not hasattr(app.state, "_storage_container")
