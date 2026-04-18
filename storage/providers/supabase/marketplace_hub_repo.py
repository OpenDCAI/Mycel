"""Supabase read model for local Hub marketplace surfaces."""

from __future__ import annotations

from typing import Any

from storage.contracts import MarketplaceHubNotFoundError, MarketplaceHubUnsupportedSortError
from storage.providers.supabase import _query as sq

_REPO = "marketplace hub repo"
_SCHEMA = "hub"


class SupabaseMarketplaceHubRepo:
    def __init__(self, client: Any) -> None:
        self._client = sq.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def list_items(
        self,
        *,
        type: str | None = None,
        q: str | None = None,
        sort: str = "downloads",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        rows = self._published_items()
        if type:
            rows = [row for row in rows if row.get("type") == type]
        if q:
            needle = q.strip().lower()
            rows = [row for row in rows if needle in _search_text(row)]

        rows = _sort_items(rows, sort)
        total = len(rows)
        start = max(page - 1, 0) * page_size
        end = start + page_size
        publishers = self._publishers_for(rows[start:end])
        return {
            "items": [self._summary(row, publishers) for row in rows[start:end]],
            "total": total,
        }

    def get_item_detail(self, item_id: str) -> dict[str, Any]:
        row = self._item(item_id)
        publishers = self._publishers_for([row])
        versions = self._versions(item_id)
        return {
            **self._summary(row, publishers),
            "versions": [
                {
                    "id": str(version["id"]),
                    "version": str(version["version"]),
                    "release_notes": version.get("changelog"),
                    "created_at": str(version["created_at"]),
                }
                for version in versions
            ],
            "parent": None,
        }

    def get_item_lineage(self, item_id: str) -> dict[str, Any]:
        self._item(item_id)
        return {"ancestors": [], "children": []}

    def get_item_version_snapshot(self, item_id: str, version: str) -> dict[str, Any]:
        rows = sq.rows(
            self._table("marketplace_versions")
            .select("id, item_id, version, content, changelog, status, created_at")
            .eq("item_id", item_id)
            .eq("version", version)
            .eq("status", "active")
            .execute(),
            _REPO,
            "get_item_version_snapshot",
        )
        if not rows:
            raise MarketplaceHubNotFoundError(f"Marketplace item version not found: {item_id}@{version}")
        return {"snapshot": rows[0]["content"]}

    def _published_items(self) -> list[dict[str, Any]]:
        rows = sq.rows(
            self._table("marketplace_items")
            .select(
                "id, publisher_id, slug, type, name, description, tags, is_public, status, "
                "latest_version, install_count, created_at, updated_at"
            )
            .eq("status", "published")
            .eq("is_public", True)
            .execute(),
            _REPO,
            "list_items",
        )
        return [dict(row) for row in rows]

    def _item(self, item_id: str) -> dict[str, Any]:
        rows = sq.rows(
            self._table("marketplace_items")
            .select(
                "id, publisher_id, slug, type, name, description, tags, is_public, status, "
                "latest_version, install_count, created_at, updated_at"
            )
            .eq("id", item_id)
            .eq("status", "published")
            .eq("is_public", True)
            .execute(),
            _REPO,
            "get_item",
        )
        if not rows:
            raise MarketplaceHubNotFoundError(f"Marketplace item not found: {item_id}")
        return dict(rows[0])

    def _versions(self, item_id: str) -> list[dict[str, Any]]:
        query = (
            self._table("marketplace_versions")
            .select("id, item_id, version, content, changelog, status, created_at")
            .eq("item_id", item_id)
            .eq("status", "active")
        )
        rows = sq.rows(sq.order(query, "created_at", desc=True, repo=_REPO, operation="list_versions").execute(), _REPO, "list_versions")
        return [dict(row) for row in rows]

    def _publishers_for(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        publisher_ids = sorted({str(row["publisher_id"]) for row in rows})
        if not publisher_ids:
            return {}
        result = sq.rows_in_chunks(
            lambda: self._table("marketplace_publishers").select("id, user_id, display_name, avatar_url, created_at"),
            "id",
            publisher_ids,
            _REPO,
            "publishers_for_items",
        )
        return {str(row["id"]): dict(row) for row in result}

    def _summary(self, row: dict[str, Any], publishers: dict[str, dict[str, Any]]) -> dict[str, Any]:
        publisher = publishers.get(str(row["publisher_id"]))
        if publisher is None:
            raise RuntimeError(f"Marketplace item {row['id']} references missing publisher {row['publisher_id']}")
        return {
            "id": str(row["id"]),
            "slug": str(row["slug"]),
            "type": str(row["type"]),
            "name": str(row["name"]),
            "description": row.get("description"),
            "avatar_url": publisher.get("avatar_url"),
            "publisher_user_id": str(publisher["user_id"]),
            "publisher_username": str(publisher["display_name"]),
            "parent_id": row.get("parent_id"),
            "download_count": int(row.get("install_count") or 0),
            "visibility": "public" if row.get("is_public") else "unlisted",
            "tags": list(row.get("tags") or []),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def _table(self, table: str) -> Any:
        return sq.schema_table(self._client, _SCHEMA, table, _REPO)


def _search_text(row: dict[str, Any]) -> str:
    values = [row.get("name"), row.get("slug"), row.get("description"), " ".join(row.get("tags") or [])]
    return " ".join(str(value).lower() for value in values if value)


def _sort_items(rows: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    if sort == "newest":
        return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)
    if sort == "downloads":
        return sorted(rows, key=lambda row: int(row.get("install_count") or 0), reverse=True)
    raise MarketplaceHubUnsupportedSortError(f"Marketplace Hub sort is not supported by hub schema: {sort}")
