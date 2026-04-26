from typing import Literal

from pydantic import BaseModel, Field


class PublishAgentUserToMarketplaceRequest(BaseModel):
    user_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    bump_type: Literal["major", "minor", "patch"] = "patch"
    release_notes: str = ""
    tags: list[str] = []
    visibility: Literal["public", "private"] = "public"


class ApplyFromMarketplaceRequest(BaseModel):
    item_id: str
    agent_user_id: str | None = None


class UpgradeFromMarketplaceRequest(BaseModel):
    user_id: str  # Agent user id
    item_id: str  # Marketplace item id


class MarketplaceSourceInfo(BaseModel):
    marketplace_item_id: str
    source_version: str


class CheckUpdatesRequest(BaseModel):
    items: list[MarketplaceSourceInfo]
