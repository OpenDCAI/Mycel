"""Marketplace request/response models (Mycel client side)."""

from typing import Literal

from pydantic import BaseModel, Field


class PublishAgentUserToMarketplaceRequest(BaseModel):
    user_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    bump_type: Literal["major", "minor", "patch"] = "patch"
    release_notes: str = ""
    tags: list[str] = []
    visibility: Literal["public", "private"] = "public"


class InstallFromMarketplaceRequest(BaseModel):
    item_id: str


class UpgradeFromMarketplaceRequest(BaseModel):
    user_id: str  # local agent user id
    item_id: str  # marketplace item id


class InstalledItemInfo(BaseModel):
    marketplace_item_id: str
    installed_version: str


class CheckUpdatesRequest(BaseModel):
    items: list[InstalledItemInfo]
