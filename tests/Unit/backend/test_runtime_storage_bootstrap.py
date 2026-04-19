from backend import runtime_storage_bootstrap


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
