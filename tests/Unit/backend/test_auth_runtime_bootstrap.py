from types import SimpleNamespace

from backend.identity.auth import runtime_bootstrap as auth_runtime_bootstrap


def _fake_storage_container():
    return SimpleNamespace(
        user_repo=lambda: "users-repo",
        agent_config_repo=lambda: "agent-config-repo",
        invite_code_repo=lambda: "invite-code-repo",
        contact_repo=lambda: "contact-repo",
        recipe_repo=lambda: "recipe-repo",
    )


def test_build_auth_runtime_state_uses_runtime_storage_state(monkeypatch):
    calls = {}
    fake_auth_factory = object()
    user_repo = "users-repo"

    class _FakeAuthService:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

    monkeypatch.setattr(auth_runtime_bootstrap, "create_supabase_auth_client", lambda: fake_auth_factory)
    monkeypatch.setattr(auth_runtime_bootstrap, "AuthService", _FakeAuthService)

    storage_state = SimpleNamespace(
        supabase_client="supabase-client",
        storage_container=_fake_storage_container(),
    )

    state = auth_runtime_bootstrap.build_auth_runtime_state(storage_state, contact_repo="contact-repo")

    assert state.supabase_auth_client_factory() is fake_auth_factory
    assert isinstance(state.auth_service, _FakeAuthService)
    assert state.user_directory == user_repo
    assert calls["kwargs"] == {
        "users": "users-repo",
        "agent_configs": "agent-config-repo",
        "supabase_client": "supabase-client",
        "supabase_auth_client_factory": state.supabase_auth_client_factory,
        "invite_codes": "invite-code-repo",
        "contact_repo": "contact-repo",
        "recipe_repo": "recipe-repo",
    }


def test_build_auth_runtime_state_requires_explicit_contact_repo():
    storage_state = SimpleNamespace(
        supabase_client="supabase-client",
        storage_container=_fake_storage_container(),
    )

    try:
        auth_runtime_bootstrap.build_auth_runtime_state(storage_state)
    except TypeError as exc:
        assert "contact_repo" in str(exc)
    else:
        raise AssertionError("build_auth_runtime_state should require explicit contact_repo")


def test_attach_auth_runtime_state_returns_bundle_without_loose_state_mirrors(monkeypatch):
    fake_state = SimpleNamespace(auth_service=object(), supabase_auth_client_factory=object(), user_directory=object())
    app = type("_App", (), {"state": type("_State", (), {})()})()

    monkeypatch.setattr(auth_runtime_bootstrap, "build_auth_runtime_state", lambda _storage_state, *, contact_repo: fake_state)

    result = auth_runtime_bootstrap.attach_auth_runtime_state(app, storage_state=object(), contact_repo=object())

    assert result is fake_state
    assert app.state.auth_runtime_state is fake_state
    assert not hasattr(app.state, "auth_service")
    assert not hasattr(app.state, "_supabase_auth_client_factory")
