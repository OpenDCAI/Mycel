from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.web.routers import contacts as contacts_router
from storage.contracts import ContactEdgeRow


class _FakeContactRepo:
    def __init__(self) -> None:
        self.rows: list[ContactEdgeRow] = []
        self.deleted: list[tuple[str, str]] = []

    def list_for_user(self, source_user_id: str) -> list[ContactEdgeRow]:
        return [row for row in self.rows if row.source_user_id == source_user_id]

    def upsert(self, row: ContactEdgeRow) -> None:
        self.rows.append(row)

    def delete(self, source_user_id: str, target_user_id: str) -> None:
        self.deleted.append((source_user_id, target_user_id))


@pytest.mark.asyncio
async def test_list_contacts_exposes_directed_user_edge_shape() -> None:
    repo = _FakeContactRepo()
    repo.rows.append(
        ContactEdgeRow(
            source_user_id="user-a",
            target_user_id="user-b",
            kind="hire",
            state="pending",
            muted=True,
            blocked=False,
            created_at=1.0,
            updated_at=2.0,
        )
    )

    payload = await contacts_router.list_contacts(
        user_id="user-a",
        contact_repo=repo,
    )

    assert payload == [
        {
            "source_user_id": "user-a",
            "target_user_id": "user-b",
            "kind": "hire",
            "state": "pending",
            "muted": True,
            "blocked": False,
            "created_at": 1.0,
            "updated_at": 2.0,
        }
    ]


@pytest.mark.asyncio
async def test_set_contact_persists_directed_edge_contract() -> None:
    repo = _FakeContactRepo()

    result = await contacts_router.set_contact(
        contacts_router.SetContactBody(target_user_id="user-b", kind="blocked", state="active"),
        user_id="user-a",
        contact_repo=repo,
    )

    assert result == {"status": "ok", "kind": "blocked", "state": "active"}
    assert len(repo.rows) == 1
    row = repo.rows[0]
    assert row.source_user_id == "user-a"
    assert row.target_user_id == "user-b"
    assert row.kind == "blocked"
    assert row.state == "active"


@pytest.mark.asyncio
async def test_delete_contact_uses_directed_user_ids() -> None:
    repo = _FakeContactRepo()

    result = await contacts_router.delete_contact(
        "user-b",
        user_id="user-a",
        contact_repo=repo,
    )

    assert result == {"status": "deleted"}
    assert repo.deleted == [("user-a", "user-b")]


@pytest.mark.asyncio
async def test_list_contacts_fails_loud_when_contact_repo_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await contacts_router.list_contacts(
            user_id="user-a",
            contact_repo=None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "chat bootstrap not attached: contact_repo"


@pytest.mark.asyncio
async def test_set_contact_fails_loud_when_contact_repo_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await contacts_router.set_contact(
            contacts_router.SetContactBody(target_user_id="user-b", kind="blocked", state="active"),
            user_id="user-a",
            contact_repo=None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "chat bootstrap not attached: contact_repo"


@pytest.mark.asyncio
async def test_delete_contact_fails_loud_when_contact_repo_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await contacts_router.delete_contact(
            "user-b",
            user_id="user-a",
            contact_repo=None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "chat bootstrap not attached: contact_repo"
