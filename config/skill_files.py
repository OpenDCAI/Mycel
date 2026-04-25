from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _normalize_skill_file_path(path: str, *, context: str) -> str:
    normalized_path = path.replace("\\", "/")
    parts = normalized_path.split("/")
    if not normalized_path.strip() or any(part == "" for part in parts):
        raise ValueError(f"{context} path must be a relative file path")
    return normalized_path


def normalize_skill_file_map(files: Mapping[Any, Any], *, context: str) -> dict[str, str]:
    return normalize_skill_file_entries(files.items(), context=context)


def normalize_skill_file_entries(entries: Iterable[tuple[Any, Any]], *, context: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for path, content in entries:
        if not isinstance(path, str):
            raise ValueError(f"{context} path must be a string")
        normalized_path = _normalize_skill_file_path(path, context=context)
        if normalized_path in result:
            raise ValueError(f"{context} contain duplicate path after normalization: {normalized_path}")
        if not isinstance(content, str):
            raise ValueError(f"{context} content must be a string: {normalized_path}")
        result[normalized_path] = content
    return result
