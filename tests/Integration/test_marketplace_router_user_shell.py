from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.models.marketplace import PublishAgentUserToMarketplaceRequest, UpgradeFromMarketplaceRequest
from backend.web.routers import marketplace as marketplace_router


def test_marketplace_router_exposes_agent_user_publish_not_generic_publish() -> None:
    paths = {route.path for route in marketplace_router.router.routes}
    assert "/api/marketplace/publish-agent-user" in paths
    assert "/api/marketplace/publish" not in paths


@pytest.mark.asyncio
async def test_publish_agent_user_to_marketplace_uses_user_repo_not_member_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(marketplace_router.marketplace_client, "publish", lambda **kwargs: seen.update(kwargs) or {"ok": True})
    monkeypatch.setattr(
        "backend.web.services.profile_service.get_profile",
        lambda user=None: (
            (_ for _ in ()).throw(AssertionError("config profile fallback not allowed")) if user is None else {"name": user.display_name}
        ),
    )

    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: (
            SimpleNamespace(id=user_id, owner_user_id="owner-1")
            if user_id == "agent-1"
            else SimpleNamespace(id=user_id, display_name="owner-name", email="owner@example.com")
            if user_id == "owner-1"
            else None
        )
    )
    agent_config_repo = SimpleNamespace()
    req = PublishAgentUserToMarketplaceRequest(user_id="agent-1")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=user_repo,
                agent_config_repo=agent_config_repo,
            )
        )
    )

    result = await marketplace_router.publish_agent_user_to_marketplace(req=req, user_id="owner-1", request=request)

    assert result == {"ok": True}
    assert seen["user_id"] == "agent-1"
    assert seen["type_"] == "member"
    assert seen["publisher_user_id"] == "owner-1"
    assert seen["publisher_username"] == "owner-name"
    assert seen["user_repo"] is user_repo
    assert seen["agent_config_repo"] is agent_config_repo


@pytest.mark.asyncio
async def test_upgrade_from_marketplace_uses_user_repo_not_member_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(marketplace_router.marketplace_client, "upgrade", lambda **kwargs: seen.update(kwargs) or {"ok": True})

    req = UpgradeFromMarketplaceRequest(user_id="agent-1", item_id="item-1")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=SimpleNamespace(
                    get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-1") if user_id == "agent-1" else None
                ),
                agent_config_repo=SimpleNamespace(),
            )
        )
    )

    result = await marketplace_router.upgrade_from_marketplace(req=req, user_id="owner-1", request=request)

    assert result == {"ok": True}
    assert seen["user_id"] == "agent-1"
    assert seen["item_id"] == "item-1"
    assert seen["owner_user_id"] == "owner-1"
    assert seen["user_repo"] is request.app.state.user_repo
    assert seen["agent_config_repo"] is request.app.state.agent_config_repo


@pytest.mark.asyncio
async def test_download_from_marketplace_uses_user_and_agent_config_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(marketplace_router.marketplace_client, "download", lambda **kwargs: seen.update(kwargs) or {"ok": True})

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=SimpleNamespace(),
                agent_config_repo=SimpleNamespace(),
            )
        )
    )
    req = SimpleNamespace(item_id="item-1")

    result = await marketplace_router.download_from_marketplace(req=req, user_id="owner-1", request=request)

    assert result == {"ok": True}
    assert seen["item_id"] == "item-1"
    assert seen["owner_user_id"] == "owner-1"
    assert seen["user_repo"] is request.app.state.user_repo
    assert seen["agent_config_repo"] is request.app.state.agent_config_repo


@pytest.mark.asyncio
async def test_verify_user_ownership_raises_when_user_repo_row_not_owned() -> None:
    user_repo = SimpleNamespace(get_by_id=lambda _user_id: SimpleNamespace(id="agent-1", owner_user_id="owner-2"))

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router._verify_user_ownership("agent-1", "owner-1", user_repo)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized to publish this user"
