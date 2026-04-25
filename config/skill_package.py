from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from config.agent_config_types import SkillPackage


def build_skill_package(
    *,
    owner_user_id: str,
    skill_id: str,
    version: str,
    skill_md: str,
    files: dict[str, str],
    source: dict[str, Any],
    created_at: datetime,
) -> SkillPackage:
    package_hash = build_skill_package_hash(skill_md, files)
    return SkillPackage(
        id=package_hash.removeprefix("sha256:"),
        owner_user_id=owner_user_id,
        skill_id=skill_id,
        version=version,
        hash=package_hash,
        manifest=build_skill_package_manifest(skill_md, files),
        skill_md=skill_md,
        files=files,
        source=source,
        created_at=created_at,
    )


def build_skill_package_manifest(skill_md: str, files: dict[str, str]) -> dict[str, Any]:
    return {
        "entry": "SKILL.md",
        "files": [
            {
                "path": path,
                "sha256": _sha256_text(files[path]),
                "size_bytes": len(files[path].encode("utf-8")),
            }
            for path in sorted(files)
        ],
    }


def build_skill_package_hash(skill_md: str, files: dict[str, str]) -> str:
    package_payload = {
        "skill_md": skill_md,
        "files": {path: files[path] for path in sorted(files)},
    }
    encoded = json.dumps(package_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
