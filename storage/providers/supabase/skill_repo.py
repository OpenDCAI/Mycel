"""Supabase repository for Skills stored in the Library."""

from __future__ import annotations

from typing import Any

from config.agent_config_types import Skill, SkillPackage
from storage.providers.supabase import _query as q

_REPO = "skill repo"
_SCHEMA = "library"
_SKILLS_TABLE = "skills"
_PACKAGES_TABLE = "skill_packages"


class SupabaseSkillRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _skills_table(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _SKILLS_TABLE, _REPO)

    def _packages_table(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _PACKAGES_TABLE, _REPO)

    def list_for_owner(self, owner_user_id: str) -> list[Skill]:
        rows = q.rows(
            self._skills_table().select("*").eq("owner_user_id", owner_user_id).execute(),
            _REPO,
            "list_for_owner",
        )
        return [_skill_from_row(row) for row in rows]

    def get_by_id(self, owner_user_id: str, skill_id: str) -> Skill | None:
        rows = q.rows(
            self._skills_table().select("*").eq("owner_user_id", owner_user_id).eq("id", skill_id).execute(),
            _REPO,
            "get_by_id",
        )
        if not rows:
            return None
        return _skill_from_row(rows[0])

    def upsert(self, skill: Skill) -> Skill:
        payload = skill.model_dump(mode="json")
        payload["source_json"] = payload.pop("source")
        rows = q.rows(
            self._skills_table().upsert(payload).execute(),
            _REPO,
            "upsert",
        )
        if not rows:
            raise RuntimeError("Supabase skill repo expected upsert to return a row")
        return _skill_from_row(rows[0])

    def create_package(self, package: SkillPackage) -> SkillPackage:
        payload = package.model_dump(mode="json")
        payload["manifest_json"] = payload.pop("manifest")
        payload["files_json"] = payload.pop("files")
        payload["source_json"] = payload.pop("source")
        rows = q.rows(
            self._packages_table().upsert(payload).execute(),
            _REPO,
            "create_package",
        )
        if not rows:
            raise RuntimeError("Supabase skill repo expected package upsert to return a row")
        return _package_from_row(rows[0])

    def get_package(self, owner_user_id: str, package_id: str) -> SkillPackage | None:
        rows = q.rows(
            self._packages_table().select("*").eq("owner_user_id", owner_user_id).eq("id", package_id).execute(),
            _REPO,
            "get_package",
        )
        if not rows:
            return None
        return _package_from_row(rows[0])

    def select_package(self, owner_user_id: str, skill_id: str, package_id: str) -> None:
        package = self.get_package(owner_user_id, package_id)
        if package is None:
            raise RuntimeError(f"Skill package not found: {package_id}")
        if package.skill_id != skill_id:
            raise RuntimeError(f"Skill package {package_id} does not belong to Skill {skill_id}")
        self._skills_table().update({"package_id": package_id}).eq("owner_user_id", owner_user_id).eq("id", skill_id).execute()

    def delete(self, owner_user_id: str, skill_id: str) -> None:
        self._skills_table().delete().eq("owner_user_id", owner_user_id).eq("id", skill_id).execute()


def _skill_from_row(row: dict[str, Any]) -> Skill:
    return Skill(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        name=row["name"],
        description=_text(row, "description", table="library.skills"),
        package_id=row.get("package_id"),
        source=_json_object(row, "source_json", table="library.skills"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _json_object(row: dict[str, Any], column: str, *, table: str) -> dict[str, Any]:
    value = row[column]
    if not isinstance(value, dict):
        raise RuntimeError(f"{table}.{column} must be a JSON object")
    return value.copy()


def _text(row: dict[str, Any], column: str, *, table: str) -> str:
    value = row[column]
    if not isinstance(value, str):
        raise RuntimeError(f"{table}.{column} must be text")
    return value


def _package_from_row(row: dict[str, Any]) -> SkillPackage:
    return SkillPackage(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        skill_id=row["skill_id"],
        version=row["version"],
        hash=row["hash"],
        manifest=_json_object(row, "manifest_json", table="library.skill_packages"),
        skill_md=row["skill_md"],
        files=_json_object(row, "files_json", table="library.skill_packages"),
        source=_json_object(row, "source_json", table="library.skill_packages"),
        created_at=row["created_at"],
    )
