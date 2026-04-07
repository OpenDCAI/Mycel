from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.models.marketplace import PublishToMarketplaceRequest, UpgradeFromMarketplaceRequest
from backend.web.routers import marketplace as marketplace_router


@pytest.mark.asyncio
async def test_require_owned_member_repo_returns_repo_after_verification(monkeypatch: pytest.MonkeyPatch):
    member_repo = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(member_repo=member_repo)))
    calls: list[tuple[str, str, object]] = []

    async def fake_verify(member_id: str, user_id: str, repo: object) -> None:
        calls.append((member_id, user_id, repo))

    monkeypatch.setattr(marketplace_router, "_verify_member_ownership", fake_verify)

    result = await marketplace_router._require_owned_member_repo(request, "member-1", "user-1")

    assert result is member_repo
    assert calls == [("member-1", "user-1", member_repo)]


@pytest.mark.asyncio
async def test_publish_to_marketplace_uses_owned_member_repo_shell(monkeypatch: pytest.MonkeyPatch):
    member_repo = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(member_repo=member_repo)))
    req = PublishToMarketplaceRequest(member_id="member-1")
    preflight_calls: list[tuple[object, str, str]] = []
    publish_calls: list[dict[str, object]] = []

    async def fake_require_owned_member_repo(request_obj: object, member_id: str, user_id: str):
        preflight_calls.append((request_obj, member_id, user_id))
        return member_repo

    def fake_get_profile():
        return {"name": "tester"}

    def fake_publish(**kwargs: object):
        publish_calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(marketplace_router, "_require_owned_member_repo", fake_require_owned_member_repo)
    monkeypatch.setattr(marketplace_router.marketplace_client, "publish", fake_publish)
    monkeypatch.setattr("backend.web.services.profile_service.get_profile", fake_get_profile)

    result = await marketplace_router.publish_to_marketplace(req=req, user_id="user-1", request=request)

    assert result == {"ok": True}
    assert preflight_calls == [(request, "member-1", "user-1")]
    assert publish_calls == [
        {
            "member_id": "member-1",
            "type_": "member",
            "bump_type": "patch",
            "release_notes": "",
            "tags": [],
            "visibility": "public",
            "publisher_user_id": "user-1",
            "publisher_username": "tester",
        }
    ]


@pytest.mark.asyncio
async def test_upgrade_from_marketplace_uses_owned_member_repo_shell(monkeypatch: pytest.MonkeyPatch):
    member_repo = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(member_repo=member_repo)))
    req = UpgradeFromMarketplaceRequest(member_id="member-1", item_id="item-1")
    preflight_calls: list[tuple[object, str, str]] = []
    upgrade_calls: list[dict[str, object]] = []

    async def fake_require_owned_member_repo(request_obj: object, member_id: str, user_id: str):
        preflight_calls.append((request_obj, member_id, user_id))
        return member_repo

    def fake_upgrade(**kwargs: object):
        upgrade_calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(marketplace_router, "_require_owned_member_repo", fake_require_owned_member_repo)
    monkeypatch.setattr(marketplace_router.marketplace_client, "upgrade", fake_upgrade)

    result = await marketplace_router.upgrade_from_marketplace(req=req, user_id="user-1", request=request)

    assert result == {"ok": True}
    assert preflight_calls == [(request, "member-1", "user-1")]
    assert upgrade_calls == [
        {
            "member_id": "member-1",
            "item_id": "item-1",
            "owner_user_id": "user-1",
        }
    ]
