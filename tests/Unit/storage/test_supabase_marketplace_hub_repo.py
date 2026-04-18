from __future__ import annotations

import pytest

from storage.contracts import MarketplaceHubNotFoundError, MarketplaceHubUnsupportedSortError
from storage.providers.supabase.marketplace_hub_repo import SupabaseMarketplaceHubRepo
from tests.fakes.supabase import FakeSupabaseClient


def _repo() -> SupabaseMarketplaceHubRepo:
    return SupabaseMarketplaceHubRepo(
        FakeSupabaseClient(
            tables={
                "hub.marketplace_publishers": [
                    {
                        "id": "publisher-1",
                        "user_id": "system",
                        "display_name": "Mycel Official",
                        "avatar_url": None,
                        "created_at": "2026-03-31T05:07:12+00:00",
                    }
                ],
                "hub.marketplace_items": [
                    {
                        "id": "item-1",
                        "publisher_id": "publisher-1",
                        "slug": "architecture-patterns",
                        "type": "skill",
                        "name": "architecture-patterns",
                        "description": "Architecture patterns",
                        "tags": ["backend"],
                        "is_public": True,
                        "status": "published",
                        "latest_version": "1.0.0",
                        "install_count": 4,
                        "created_at": "2026-03-31T05:13:49+00:00",
                        "updated_at": "2026-03-31T05:13:49+00:00",
                    },
                    {
                        "id": "item-hidden",
                        "publisher_id": "publisher-1",
                        "slug": "hidden",
                        "type": "skill",
                        "name": "hidden",
                        "description": "Hidden draft",
                        "tags": [],
                        "is_public": True,
                        "status": "draft",
                        "latest_version": "1.0.0",
                        "install_count": 99,
                        "created_at": "2026-03-31T05:13:50+00:00",
                        "updated_at": "2026-03-31T05:13:50+00:00",
                    },
                ],
                "hub.marketplace_versions": [
                    {
                        "id": "version-1",
                        "item_id": "item-1",
                        "version": "1.0.0",
                        "changelog": "Initial release",
                        "content": {"content": "# Architecture Patterns", "meta": {"name": "architecture-patterns"}},
                        "status": "active",
                        "created_at": "2026-03-31T05:13:50+00:00",
                    }
                ],
            }
        )
    )


def test_list_items_projects_published_hub_rows_to_marketplace_payload() -> None:
    payload = _repo().list_items(type="skill", q="architecture", sort="downloads", page=1, page_size=20)

    assert payload == {
        "items": [
            {
                "id": "item-1",
                "slug": "architecture-patterns",
                "type": "skill",
                "name": "architecture-patterns",
                "description": "Architecture patterns",
                "avatar_url": None,
                "publisher_user_id": "system",
                "publisher_username": "Mycel Official",
                "parent_id": None,
                "download_count": 4,
                "visibility": "public",
                "tags": ["backend"],
                "created_at": "2026-03-31T05:13:49+00:00",
                "updated_at": "2026-03-31T05:13:49+00:00",
            }
        ],
        "total": 1,
    }


def test_item_detail_includes_versions_and_snapshot() -> None:
    repo = _repo()

    detail = repo.get_item_detail("item-1")
    snapshot = repo.get_item_version_snapshot("item-1", "1.0.0")

    assert detail["versions"] == [
        {
            "id": "version-1",
            "version": "1.0.0",
            "release_notes": "Initial release",
            "created_at": "2026-03-31T05:13:50+00:00",
        }
    ]
    assert detail["parent"] is None
    assert snapshot == {"snapshot": {"content": "# Architecture Patterns", "meta": {"name": "architecture-patterns"}}}


def test_missing_item_fails_loudly() -> None:
    with pytest.raises(MarketplaceHubNotFoundError, match="Marketplace item not found: missing"):
        _repo().get_item_detail("missing")


def test_unsupported_featured_sort_fails_loudly() -> None:
    with pytest.raises(MarketplaceHubUnsupportedSortError, match="sort is not supported"):
        _repo().list_items(sort="featured")
