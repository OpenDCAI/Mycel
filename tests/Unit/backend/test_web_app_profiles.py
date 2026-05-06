import pytest

from backend.web.app_factory import RuntimeProfile, create_app, resolve_runtime_profile


def _paths(profile: RuntimeProfile) -> set[str]:
    return set(create_app(profile=profile, lifespan_context=None).openapi()["paths"])


def test_default_runtime_profile_is_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYCEL_RUNTIME_PROFILE", raising=False)

    assert resolve_runtime_profile() is RuntimeProfile.FULL


def test_unknown_runtime_profile_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYCEL_RUNTIME_PROFILE", "tiny")

    with pytest.raises(RuntimeError, match="MYCEL_RUNTIME_PROFILE"):
        resolve_runtime_profile()


def test_full_profile_preserves_current_web_backend_surface() -> None:
    paths = _paths(RuntimeProfile.FULL)

    assert "/api/auth/guest" in paths
    assert "/api/chats" in paths
    assert any(path.startswith("/api/threads") for path in paths)
    assert any(path.startswith("/api/sandbox") for path in paths)
    assert any(path.startswith("/api/panel") for path in paths)
    assert any(path.startswith("/api/monitor") for path in paths)
    assert any(path.startswith("/api/resources") for path in paths)
    assert any(path.startswith("/api/marketplace") for path in paths)


def test_communication_profile_mounts_only_auth_chat_and_social_surfaces() -> None:
    paths = _paths(RuntimeProfile.COMMUNICATION)

    assert "/api/auth/guest" in paths
    assert "/api/auth/external-users" in paths
    assert "/api/chats" in paths
    assert "/api/runtime/inbox/drain" in paths
    assert "/api/relationships" in paths
    assert "/api/conversations" in paths
    assert "/api/contacts" in paths
    assert "/api/users" in paths

    excluded_prefixes = (
        "/api/invite-codes",
        "/api/marketplace",
        "/api/monitor",
        "/api/panel",
        "/api/resources",
        "/api/sandbox",
        "/api/settings",
        "/api/threads",
        "/api/webhooks",
    )
    leaked = sorted(path for path in paths if path.startswith(excluded_prefixes))

    assert leaked == []
