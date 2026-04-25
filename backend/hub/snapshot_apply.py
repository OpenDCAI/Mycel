"""Apply Hub AgentSnapshot payloads into AgentConfig aggregates."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from config.agent_config_resolver import validate_resolved_skill_content
from config.agent_config_types import AgentConfig, AgentSkill, AgentSnapshot, ResolvedSkill, Skill, SkillPackage
from config.skill_package import build_skill_package_hash, build_skill_package_manifest
from storage.utils import generate_skill_id

SNAPSHOT_SKILL_SOURCE_ID_KEY = "snapshot_skill_id"


def _required_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a string")
    return value.strip()


def _snapshot_source_skill(skills: list[Skill], marketplace_item_id: str, snapshot_skill_id: str) -> Skill | None:
    for skill in skills:
        if (
            skill.source.get("marketplace_item_id") == marketplace_item_id
            and skill.source.get(SNAPSHOT_SKILL_SOURCE_ID_KEY) == snapshot_skill_id
        ):
            return skill
    return None


def _materialize_snapshot_skills(
    *,
    skills: list[ResolvedSkill],
    owner_user_id: str,
    marketplace_item_id: str,
    source_version: str,
    source_at: int,
    skill_repo: Any = None,
) -> list[AgentSkill]:
    if not skills:
        return []
    if skill_repo is None:
        raise RuntimeError("skill_repo is required to apply snapshot Skills")

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for snapshot_skill in skills:
        validate_resolved_skill_content(snapshot_skill)
        if snapshot_skill.id in seen_ids:
            raise ValueError(f"Duplicate Skill id in snapshot: {snapshot_skill.id}")
        seen_ids.add(snapshot_skill.id)
        if snapshot_skill.name in seen_names:
            raise ValueError(f"Duplicate Skill name in snapshot: {snapshot_skill.name}")
        seen_names.add(snapshot_skill.name)

    result: list[AgentSkill] = []
    timestamp = datetime.now(UTC)
    library_skills = skill_repo.list_for_owner(owner_user_id)
    for snapshot_skill in skills:
        snapshot_skill_id = _required_text(snapshot_skill.id, label="Snapshot Skill id")
        existing = _snapshot_source_skill(library_skills, marketplace_item_id, snapshot_skill_id)
        if existing is not None and existing.name != snapshot_skill.name:
            raise ValueError("Snapshot Skill frontmatter name must match existing Skill name")
        if existing is None:
            skill_id = generate_skill_id()
            if skill_repo.get_by_id(owner_user_id, skill_id) is not None:
                raise RuntimeError("Generated Skill id already exists")
            for library_skill in library_skills:
                if library_skill.name == snapshot_skill.name:
                    raise ValueError("Snapshot Skill name already exists under a different Library id")
        else:
            skill_id = existing.id

        source = {
            "marketplace_item_id": marketplace_item_id,
            SNAPSHOT_SKILL_SOURCE_ID_KEY: snapshot_skill_id,
            "source_version": source_version,
            "source_at": source_at,
        }
        # @@@snapshot-skill-materialization - AgentConfig stores package bindings; Hub snapshots carry resolved Skill content.
        skill = skill_repo.upsert(
            Skill(
                id=skill_id,
                owner_user_id=owner_user_id,
                name=snapshot_skill.name,
                description=snapshot_skill.description,
                source=source,
                created_at=getattr(existing, "created_at", timestamp),
                updated_at=timestamp,
            )
        )
        package_hash = build_skill_package_hash(snapshot_skill.content, snapshot_skill.files)
        package = skill_repo.create_package(
            SkillPackage(
                id=package_hash.removeprefix("sha256:"),
                owner_user_id=owner_user_id,
                skill_id=skill.id,
                version=snapshot_skill.version,
                hash=package_hash,
                manifest=build_skill_package_manifest(snapshot_skill.content, snapshot_skill.files),
                skill_md=snapshot_skill.content,
                files=snapshot_skill.files,
                source=source,
                created_at=timestamp,
            )
        )
        skill_repo.select_package(owner_user_id, skill.id, package.id)
        result.append(
            AgentSkill(
                skill_id=skill.id,
                package_id=package.id,
                name=snapshot_skill.name,
                description=snapshot_skill.description,
            )
        )
    return result


def apply_snapshot(
    *,
    snapshot: dict,
    marketplace_item_id: str,
    source_version: str,
    owner_user_id: str,
    existing_user_id: str | None = None,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> str:
    from storage.contracts import UserRow, UserType
    from storage.utils import generate_agent_config_id, generate_agent_user_id

    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required to apply marketplace user snapshot")

    marketplace_item_id = _required_text(marketplace_item_id, label="marketplace_item_id")
    source_version = _required_text(source_version, label="source_version")
    parsed = AgentSnapshot.model_validate(snapshot)
    resolved = parsed.agent
    now = time.time()

    if existing_user_id:
        user_id = existing_user_id
        user = user_repo.get_by_id(user_id)
        if user is None or user.agent_config_id is None:
            raise RuntimeError(f"Agent user {user_id} is missing agent_config_id")
        agent_config_id = user.agent_config_id
        user_repo.update(user_id, display_name=resolved.name)
    else:
        user_id = generate_agent_user_id()
        agent_config_id = generate_agent_config_id()
        user_repo.create(
            UserRow(
                id=user_id,
                type=UserType.AGENT,
                display_name=resolved.name,
                owner_user_id=owner_user_id,
                agent_config_id=agent_config_id,
                created_at=now,
            )
        )

    source_at = int(now * 1000)
    skills = _materialize_snapshot_skills(
        skills=resolved.skills,
        owner_user_id=owner_user_id,
        marketplace_item_id=marketplace_item_id,
        source_version=source_version,
        source_at=source_at,
        skill_repo=skill_repo,
    )

    meta = dict(resolved.meta)
    meta["source"] = {
        "marketplace_item_id": marketplace_item_id,
        "source_version": source_version,
        "source_at": source_at,
        "modified": False,
    }

    agent_config_repo.save_agent_config(
        AgentConfig(
            id=agent_config_id,
            owner_user_id=owner_user_id,
            agent_user_id=user_id,
            name=resolved.name,
            description=resolved.description,
            model=resolved.model,
            tools=resolved.tools,
            system_prompt=resolved.system_prompt,
            status="active",
            version=source_version,
            runtime_settings=resolved.runtime_settings,
            compact=resolved.compact,
            skills=skills,
            rules=resolved.rules,
            sub_agents=resolved.sub_agents,
            mcp_servers=resolved.mcp_servers,
            meta=meta,
        )
    )
    return user_id
