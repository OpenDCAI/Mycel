"""Process-local storage container cache."""

from __future__ import annotations

from storage.container import StorageContainer
from storage.runtime import build_storage_container

_cached_container: StorageContainer | None = None


def get_storage_container() -> StorageContainer:
    global _cached_container
    if _cached_container is not None:
        return _cached_container
    _cached_container = build_storage_container()
    return _cached_container
