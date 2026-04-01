"""Marketplace request/response models (Mycel client side)."""

from typing import Literal

from pydantic import BaseModel, Field


class PublishToMarketplaceRequest(BaseModel):
    member_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    type: Literal["member", "agent", "skill", "env"] = "member"
    bump_type: Literal["major", "minor", "patch"] = "patch"
    release_notes: str = ""
    tags: list[str] = []
    visibility: Literal["public", "private"] = "public"


class InstallFromMarketplaceRequest(BaseModel):
    item_id: str


class UpgradeFromMarketplaceRequest(BaseModel):
    member_id: str  # local member id
    item_id: str  # marketplace item id


class InstalledItemInfo(BaseModel):
    marketplace_item_id: str
    installed_version: str


class CheckUpdatesRequest(BaseModel):
    items: list[InstalledItemInfo]
