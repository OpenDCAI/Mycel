"""Members API router — DB-backed member listing + directory."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from backend.web.core.dependencies import get_app, get_current_member_id
from core.agents.communication.directory_service import DirectoryService

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("")
async def list_members(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
) -> list[dict[str, Any]]:
    """List members visible to the authenticated user: self + contacts."""
    repo = app.state.member_repo
    contact_repo = app.state.contact_repo

    results = []

    # Own member
    me = repo.get_by_id(member_id)
    if me:
        results.append(_row_to_dict(me))

    # Contacts (agent members)
    for contact in contact_repo.list_by_owner(member_id):
        m = repo.get_by_id(contact.contact_id)
        if m:
            results.append(_row_to_dict(m))

    return results


# @@@member-directory - unified discovery endpoint backed by DirectoryService
@router.get("/directory")
async def directory(
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[Any, Depends(get_app)],
    type: str | None = Query(None, description="Filter by MemberType: mycel_agent, human, openclaw_agent"),
    search: str | None = Query(None, description="Case-insensitive substring search on name or owner name"),
) -> dict[str, list[dict[str, Any]]]:
    """Browse the member directory. Returns {contacts: [...], others: [...]}.

    Same logic as the agent's logbook(directory=true) — shared DirectoryService.
    """
    svc = DirectoryService(app.state.member_repo, app.state.contact_repo)
    result = svc.browse(member_id, type_filter=type, search=search)

    def _entry_dict(e: Any) -> dict[str, Any]:
        return {
            "id": e.id,
            "name": e.name,
            "type": e.type,
            "description": e.description,
            "owner": e.owner,
            "is_contact": e.is_contact,
        }

    return {
        "contacts": [_entry_dict(e) for e in result.contacts],
        "others": [_entry_dict(e) for e in result.others],
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type.value if hasattr(row.type, "value") else row.type,
        "avatar": row.avatar,
        "description": row.description,
        "config_dir": row.config_dir,
        "created_at": row.created_at,
    }
