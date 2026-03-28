"""Volume source abstraction — where files physically live.

VolumeSource can be backed by host filesystem (HostVolume) or
provider-managed storage (DaytonaVolume). Serialized as JSON to DB.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class VolumeSource(Protocol):
    """Abstract persistent storage backend."""

    def save_file(self, relative_path: str, content: bytes) -> dict[str, Any]: ...
    def list_files(self) -> list[dict[str, Any]]: ...
    def resolve_file(self, relative_path: str) -> Path: ...
    def delete_file(self, relative_path: str) -> None: ...

    @property
    def host_path(self) -> Path | None:
        """Host filesystem path for sync. None if no host backing."""
        ...

    def cleanup(self) -> None: ...
    def serialize(self) -> dict[str, Any]: ...


def _resolve_safe_path(base: Path, relative_path: str) -> Path:
    """Resolve relative path with traversal protection."""
    # @@@path-boundary - Reject traversal so callers cannot escape the volume root
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError(f"Path must be relative: {relative_path}")
    candidate = (base / requested).resolve()
    candidate.relative_to(base)
    return candidate


class HostVolume:
    """Host filesystem volume. Used by Local, Docker, E2B, Daytona fallback."""

    def __init__(self, base_path: Path):
        self.base_path = base_path.expanduser().resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    @property
    def host_path(self) -> Path:
        return self.base_path

    def save_file(self, relative_path: str, content: bytes) -> dict[str, Any]:
        target = _resolve_safe_path(self.base_path, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {
            "relative_path": str(Path(relative_path)),
            "absolute_path": str(target),
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def list_files(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if not self.base_path.is_dir():
            return entries
        for item in sorted(self.base_path.rglob("*")):
            if not item.is_file():
                continue
            entries.append({
                "relative_path": str(item.relative_to(self.base_path)),
                "size_bytes": item.stat().st_size,
                "updated_at": datetime.fromtimestamp(item.stat().st_mtime, tz=UTC).isoformat(),
            })
        return entries

    def resolve_file(self, relative_path: str) -> Path:
        target = _resolve_safe_path(self.base_path, relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return target

    def delete_file(self, relative_path: str) -> None:
        target = _resolve_safe_path(self.base_path, relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        target.unlink()

    def cleanup(self) -> None:
        if self.base_path.exists():
            shutil.rmtree(self.base_path)

    def serialize(self) -> dict[str, Any]:
        return {"type": "host", "path": str(self.base_path)}


class DaytonaVolume:
    """Daytona-managed volume with host staging buffer.

    Files persist in Daytona managed volume on the server.
    Uses host dir as staging for uploads (sync transfers to volume).
    Future: use Daytona API for direct writes, bypassing staging.
    """

    def __init__(self, staging_path: Path, volume_name: str):
        self._staging = HostVolume(staging_path)
        self.volume_name = volume_name

    @property
    def host_path(self) -> Path:
        return self._staging.base_path

    def save_file(self, relative_path: str, content: bytes) -> dict[str, Any]:
        return self._staging.save_file(relative_path, content)

    def list_files(self) -> list[dict[str, Any]]:
        return self._staging.list_files()

    def resolve_file(self, relative_path: str) -> Path:
        return self._staging.resolve_file(relative_path)

    def delete_file(self, relative_path: str) -> None:
        self._staging.delete_file(relative_path)

    def cleanup(self) -> None:
        self._staging.cleanup()

    def serialize(self) -> dict[str, Any]:
        return {
            "type": "daytona",
            "staging_path": str(self._staging.base_path),
            "volume_name": self.volume_name,
        }


def deserialize_volume_source(data: dict[str, Any]) -> VolumeSource:
    """Reconstruct VolumeSource from serialized JSON."""
    match data["type"]:
        case "host":
            return HostVolume(Path(data["path"]))
        case "daytona":
            return DaytonaVolume(
                staging_path=Path(data["staging_path"]),
                volume_name=data["volume_name"],
            )
        case _:
            raise ValueError(f"Unknown volume source type: {data['type']}")
