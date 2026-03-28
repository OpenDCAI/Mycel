"""Member volume service — persistent storage for agent members."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from backend.web.utils.helpers import _get_container
from storage.contracts import MemberVolumeRepo


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _member_volume_repo() -> MemberVolumeRepo:
    return _get_container().member_volume_repo()


def get_member_volume(member_id: str, provider_type: str) -> dict[str, Any] | None:
    repo = _member_volume_repo()
    try:
        return repo.get(member_id, provider_type)
    finally:
        repo.close()


def create_member_volume(
    member_id: str, provider_type: str, backend_ref: str, mount_path: str,
) -> dict[str, Any]:
    now = _now_utc()
    repo = _member_volume_repo()
    try:
        repo.upsert(member_id, provider_type, backend_ref, mount_path, now)
    finally:
        repo.close()
    logger.info("Created member volume: member_id=%s provider=%s ref=%s", member_id, provider_type, backend_ref)
    return {
        "member_id": member_id, "provider_type": provider_type,
        "backend_ref": backend_ref, "mount_path": mount_path, "created_at": now,
    }


def list_member_volumes(member_id: str) -> list[dict[str, Any]]:
    repo = _member_volume_repo()
    try:
        return repo.list_by_member(member_id)
    finally:
        repo.close()


def delete_member_volume(member_id: str, provider_type: str) -> bool:
    repo = _member_volume_repo()
    try:
        deleted = repo.delete(member_id, provider_type)
    finally:
        repo.close()
    if deleted:
        logger.info("Deleted member volume: member_id=%s provider=%s", member_id, provider_type)
    return deleted


def delete_all_member_volumes(member_id: str) -> int:
    repo = _member_volume_repo()
    try:
        count = repo.delete_all_for_member(member_id)
    finally:
        repo.close()
    if count:
        logger.info("Deleted %d member volume(s) for member_id=%s", count, member_id)
    return count
