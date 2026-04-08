from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.models.marketplace import PublishToMarketplaceRequest, UpgradeFromMarketplaceRequest
from backend.web.routers import marketplace as marketplace_router


@pytest.mark.asyncio
async def test_publish_to_marketplace_uses_user_repo_not_member_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(marketplace_router.marketplace_client, "publish", lambda **kwargs: seen.update(kwargs) or {"ok": True})
    monkeypatch.setattr("backend.web.services.profile_service.get_profile", lambda: {"name": "owner-name"})

    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-1") if user_id == "agent-1" else None
    )
    agent_config_repo = SimpleNamespace()
    req = PublishToMarketplaceRequest(user_id="agent-1")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                user_repo=user_repo,
                agent_config_repo=agent_config_repo,
            )
        )
    )

    result = await marketplace_router.publish_to_marketplace(req=req, user_id="owner-1", request=request)

    assert result == {"ok": True}
    assert seen["user_id"] == "agent-1"
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
                )
            )
        )
    )

    result = await marketplace_router.upgrade_from_marketplace(req=req, user_id="owner-1", request=request)

    assert result == {"ok": True}
    assert seen == {"user_id": "agent-1", "item_id": "item-1", "owner_user_id": "owner-1"}


@pytest.mark.asyncio
async def test_verify_user_ownership_raises_when_user_repo_row_not_owned() -> None:
    user_repo = SimpleNamespace(get_by_id=lambda _user_id: SimpleNamespace(id="agent-1", owner_user_id="owner-2"))

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router._verify_user_ownership("agent-1", "owner-1", user_repo)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized to publish this user"
