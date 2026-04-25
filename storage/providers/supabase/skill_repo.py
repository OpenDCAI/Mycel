"""Supabase repository for Skills stored in the Library."""

from __future__ import annotations

from typing import Any

from config.agent_config_types import Skill
from storage.providers.supabase import _query as q

_REPO = "skill repo"
_SCHEMA = "agent"
_TABLE = "skills"


class SupabaseSkillRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _TABLE, _REPO)

    def list_for_owner(self, owner_user_id: str) -> list[Skill]:
        rows = q.rows(
            self._table().select("*").eq("owner_user_id", owner_user_id).execute(),
            _REPO,
            "list_for_owner",
        )
        return [_skill_from_row(row) for row in rows]

    def get_by_id(self, owner_user_id: str, skill_id: str) -> Skill | None:
        rows = q.rows(
            self._table().select("*").eq("owner_user_id", owner_user_id).eq("id", skill_id).execute(),
            _REPO,
            "get_by_id",
        )
        if not rows:
            return None
        return _skill_from_row(rows[0])

    def upsert(self, skill: Skill) -> Skill:
        payload = skill.model_dump(mode="json")
        payload["files_json"] = payload.pop("files")
        payload["source_json"] = payload.pop("source")
        rows = q.rows(
            self._table().upsert(payload).execute(),
            _REPO,
            "upsert",
        )
        if not rows:
            raise RuntimeError("Supabase skill repo expected upsert to return a row")
        return _skill_from_row(rows[0])

    def delete(self, owner_user_id: str, skill_id: str) -> None:
        self._table().delete().eq("owner_user_id", owner_user_id).eq("id", skill_id).execute()


def _skill_from_row(row: dict[str, Any]) -> Skill:
    return Skill(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        name=row["name"],
        description=row.get("description") or "",
        version=row.get("version") or "0.1.0",
        content=row["content"],
        files=dict(row.get("files_json") or {}),
        source=dict(row.get("source_json") or {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
