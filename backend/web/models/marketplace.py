"""Marketplace request/response models (Mycel client side)."""
from pydantic import BaseModel


class PublishToMarketplaceRequest(BaseModel):
    member_id: str
    type: str = "member"
    bump_type: str = "patch"
    release_notes: str = ""
    tags: list[str] = []
    visibility: str = "public"


class InstallFromMarketplaceRequest(BaseModel):
    item_id: str
    version: str | None = None  # None = latest


class UpgradeFromMarketplaceRequest(BaseModel):
    member_id: str  # local member id
    item_id: str    # marketplace item id


class CheckUpdatesRequest(BaseModel):
    items: list[dict]  # [{marketplace_item_id, installed_version}]
