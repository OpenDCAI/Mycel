from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def normalize_skill_file_map(files: Mapping[Any, Any], *, context: str) -> dict[str, str]:
    return normalize_skill_file_entries(files.items(), context=context)


def normalize_skill_file_entries(entries: Iterable[tuple[Any, Any]], *, context: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for path, content in entries:
        normalized_path = str(path).replace("\\", "/")
        if normalized_path in result:
            raise ValueError(f"{context} contain duplicate path after normalization: {normalized_path}")
        result[normalized_path] = str(content)
    return result
