"""Supabase stub for sandbox files repository."""

from __future__ import annotations

from typing import Any


class SupabaseSandboxFilesRepo:

    def __init__(self, client: Any) -> None:
        raise NotImplementedError("SupabaseSandboxFilesRepo is not yet implemented")

    def close(self) -> None:
        raise NotImplementedError

    def create(self, sandbox_files_id: str, host_path: str, name: str | None, created_at: str) -> None:
        raise NotImplementedError

    def get(self, sandbox_files_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_all(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def delete(self, sandbox_files_id: str) -> bool:
        raise NotImplementedError
