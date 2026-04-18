from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.models.marketplace import PublishAgentUserToMarketplaceRequest, UpgradeFromMarketplaceRequest
from backend.web.routers import marketplace as marketplace_router
from storage.contracts import MarketplaceHubNotFoundError, MarketplaceHubUnsupportedSortError


def test_marketplace_router_exposes_agent_user_marketplace_routes() -> None:
    paths = {route.path for route in marketplace_router.router.routes}

    assert "/api/marketplace/publish-agent-user" in paths
    assert "/api/marketplace/items" in paths
    assert "/api/marketplace/items/{item_id}" in paths
    assert "/api/marketplace/items/{item_id}/lineage" in paths
    assert "/api/marketplace/items/{item_id}/versions/{version}" in paths


@pytest.mark.asyncio
async def test_publish_agent_user_to_marketplace_uses_user_repo_not_member_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(marketplace_router.marketplace_client, "publish", lambda **kwargs: seen.update(kwargs) or {"ok": True})
    monkeypatch.setattr(
        "backend.web.services.profile_service.get_profile",
        lambda user=None: (
            (_ for _ in ()).throw(AssertionError("profile lookup must be user-scoped")) if user is None else {"name": user.display_name}
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
async def test_list_marketplace_items_reads_local_hub_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "list_items",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("marketplace read path must not require external Hub HTTP")),
        raising=False,
    )
    hub_repo = SimpleNamespace(
        list_items=lambda **kwargs: seen.update(kwargs) or {"items": [{"id": "item-1"}], "total": 1},
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(marketplace_hub_repo=hub_repo)))

    result = await marketplace_router.list_marketplace_items(
        request=request,
        type="skill",
        q="search",
        sort="newest",
        page=2,
        page_size=10,
    )

    assert result == {"items": [{"id": "item-1"}], "total": 1}
    assert seen == {"type": "skill", "q": "search", "sort": "newest", "page": 2, "page_size": 10}


@pytest.mark.asyncio
async def test_get_marketplace_item_detail_reads_local_hub_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "get_item_detail",
        lambda _item_id: (_ for _ in ()).throw(AssertionError("marketplace read path must not require external Hub HTTP")),
        raising=False,
    )
    hub_repo = SimpleNamespace(get_item_detail=lambda item_id: {"id": item_id, "name": "Repo Item"})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(marketplace_hub_repo=hub_repo)))

    result = await marketplace_router.get_marketplace_item_detail("item-1", request=request)

    assert result == {"id": "item-1", "name": "Repo Item"}


@pytest.mark.asyncio
async def test_get_marketplace_item_lineage_reads_local_hub_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "get_item_lineage",
        lambda _item_id: (_ for _ in ()).throw(AssertionError("marketplace read path must not require external Hub HTTP")),
        raising=False,
    )
    hub_repo = SimpleNamespace(get_item_lineage=lambda item_id: {"ancestors": [], "children": [{"id": item_id}]})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(marketplace_hub_repo=hub_repo)))

    result = await marketplace_router.get_marketplace_item_lineage("item-1", request=request)

    assert result == {"ancestors": [], "children": [{"id": "item-1"}]}


@pytest.mark.asyncio
async def test_get_marketplace_item_version_snapshot_reads_local_hub_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        marketplace_router.marketplace_client,
        "get_item_version_snapshot",
        lambda _item_id, _version: (_ for _ in ()).throw(AssertionError("marketplace read path must not require external Hub HTTP")),
        raising=False,
    )
    hub_repo = SimpleNamespace(
        get_item_version_snapshot=lambda item_id, version: {"snapshot": {"meta": {"id": item_id, "version": version}}},
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(marketplace_hub_repo=hub_repo)))

    result = await marketplace_router.get_marketplace_item_version_snapshot("item-1", "1.2.3", request=request)

    assert result == {"snapshot": {"meta": {"id": "item-1", "version": "1.2.3"}}}


@pytest.mark.asyncio
async def test_get_marketplace_item_detail_maps_missing_hub_row_to_404() -> None:
    hub_repo = SimpleNamespace(
        get_item_detail=lambda _item_id: (_ for _ in ()).throw(MarketplaceHubNotFoundError("Marketplace item not found: missing-item")),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(marketplace_hub_repo=hub_repo)))

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router.get_marketplace_item_detail("missing-item", request=request)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Marketplace item not found: missing-item"


@pytest.mark.asyncio
async def test_list_marketplace_items_maps_unsupported_hub_sort_to_400() -> None:
    hub_repo = SimpleNamespace(
        list_items=lambda **_kwargs: (_ for _ in ()).throw(
            MarketplaceHubUnsupportedSortError("Marketplace Hub sort is not supported by hub schema: featured")
        ),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(marketplace_hub_repo=hub_repo)))

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router.list_marketplace_items(request=request, sort="featured")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Marketplace Hub sort is not supported by hub schema: featured"


@pytest.mark.asyncio
async def test_verify_user_ownership_raises_when_user_repo_row_not_owned() -> None:
    user_repo = SimpleNamespace(get_by_id=lambda _user_id: SimpleNamespace(id="agent-1", owner_user_id="owner-2"))

    with pytest.raises(HTTPException) as exc_info:
        await marketplace_router._verify_user_ownership("agent-1", "owner-1", user_repo)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not authorized to publish this user"
