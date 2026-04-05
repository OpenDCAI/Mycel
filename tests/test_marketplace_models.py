"""Tests for Marketplace Pydantic models."""

import pytest
from pydantic import ValidationError

from backend.web.models.marketplace import (
    CheckUpdatesRequest,
    InstallFromMarketplaceRequest,
    InstalledItemInfo,
    PublishToMarketplaceRequest,
    UpgradeFromMarketplaceRequest,
)


# ── PublishToMarketplaceRequest ──


class TestPublishToMarketplaceRequest:
    def test_valid_minimal(self):
        req = PublishToMarketplaceRequest(member_id="my-agent_01")
        assert req.member_id == "my-agent_01"
        assert req.type == "member"
        assert req.bump_type == "patch"
        assert req.visibility == "public"
        assert req.release_notes == ""
        assert req.tags == []

    def test_valid_all_fields(self):
        req = PublishToMarketplaceRequest(
            member_id="agent-x",
            type="skill",
            bump_type="minor",
            release_notes="New feature",
            tags=["ai", "tool"],
            visibility="private",
        )
        assert req.type == "skill"
        assert req.bump_type == "minor"
        assert req.visibility == "private"
        assert req.tags == ["ai", "tool"]

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            PublishToMarketplaceRequest(member_id="ok", type="unknown")

    def test_invalid_bump_type_raises(self):
        with pytest.raises(ValidationError):
            PublishToMarketplaceRequest(member_id="ok", bump_type="hotfix")

    def test_invalid_visibility_raises(self):
        with pytest.raises(ValidationError):
            PublishToMarketplaceRequest(member_id="ok", visibility="unlisted")

    def test_invalid_member_id_path_traversal(self):
        with pytest.raises(ValidationError):
            PublishToMarketplaceRequest(member_id="../evil")

    def test_invalid_member_id_slash(self):
        with pytest.raises(ValidationError):
            PublishToMarketplaceRequest(member_id="foo/bar")

    def test_invalid_member_id_spaces(self):
        with pytest.raises(ValidationError):
            PublishToMarketplaceRequest(member_id="has space")

    def test_empty_member_id_raises(self):
        with pytest.raises(ValidationError):
            PublishToMarketplaceRequest(member_id="")


# ── InstallFromMarketplaceRequest ──


class TestInstallFromMarketplaceRequest:
    def test_valid(self):
        req = InstallFromMarketplaceRequest(item_id="abc-123")
        assert req.item_id == "abc-123"

    def test_missing_item_id_raises(self):
        with pytest.raises(ValidationError):
            InstallFromMarketplaceRequest()


# ── CheckUpdatesRequest ──


class TestCheckUpdatesRequest:
    def test_valid_with_items(self):
        req = CheckUpdatesRequest(
            items=[
                InstalledItemInfo(marketplace_item_id="item-1", installed_version="1.0.0"),
                InstalledItemInfo(marketplace_item_id="item-2", installed_version="2.3.1"),
            ]
        )
        assert len(req.items) == 2
        assert req.items[0].marketplace_item_id == "item-1"
        assert req.items[1].installed_version == "2.3.1"

    def test_empty_items_list(self):
        req = CheckUpdatesRequest(items=[])
        assert req.items == []

    def test_default_items(self):
        # items is required (no default), so omitting should raise
        with pytest.raises(ValidationError):
            CheckUpdatesRequest()


# ── UpgradeFromMarketplaceRequest ──


class TestUpgradeFromMarketplaceRequest:
    def test_valid(self):
        req = UpgradeFromMarketplaceRequest(member_id="local-1", item_id="mkt-42")
        assert req.member_id == "local-1"
        assert req.item_id == "mkt-42"

    def test_missing_fields_raises(self):
        with pytest.raises(ValidationError):
            UpgradeFromMarketplaceRequest(member_id="only-one")
