"""Supabase repository for entities."""

from __future__ import annotations

from typing import Any

from storage.contracts import EntityRow, MemberRow, MemberType
from storage.providers.supabase.member_repo import SupabaseMemberRepo
from storage.providers.supabase.thread_repo import SupabaseThreadRepo

_REPO = "entity repo"


class SupabaseEntityRepo:
    def __init__(self, client: Any, *, member_repo: Any | None = None, thread_repo: Any | None = None) -> None:
        self._client = client
        self._member_repo = member_repo or SupabaseMemberRepo(client)
        self._thread_repo = thread_repo or SupabaseThreadRepo(client)

    def close(self) -> None:
        return None

    def create(self, row: EntityRow) -> None:
        # @@@entity-read-model - Supabase has no entities table; agent thread_id is derived from agent.threads.
        return None

    def get_by_id(self, id: str) -> EntityRow | None:
        member = self._member_repo.get_by_id(id)
        if member is None:
            return None
        return self._row_from_member(member)

    def get_by_member_id(self, member_id: str) -> list[EntityRow]:
        row = self.get_by_id(member_id)
        return [row] if row is not None else []

    def list_all(self) -> list[EntityRow]:
        return [self._row_from_member(member) for member in self._member_repo.list_all()]

    def list_by_type(self, entity_type: str) -> list[EntityRow]:
        return [row for row in self.list_all() if row.type == entity_type]

    def update(self, id: str, **fields: Any) -> None:
        return None

    def delete(self, id: str) -> None:
        return None

    def _row_from_member(self, member: MemberRow) -> EntityRow:
        entity_type = "agent" if member.type is MemberType.MYCEL_AGENT else "human"
        thread_id = None
        if entity_type == "agent":
            main_thread = self._thread_repo.get_main_thread(member.id)
            thread_id = main_thread["id"] if main_thread is not None else None
        return EntityRow(
            id=member.id,
            type=entity_type,
            member_id=member.id,
            name=member.name,
            avatar=member.avatar,
            thread_id=thread_id,
            created_at=member.created_at,
        )
