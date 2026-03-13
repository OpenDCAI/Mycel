"""DirectoryService — shared member discovery for humans and agents.

One service, two consumers: the HTTP endpoint and the logbook tool both call
browse() to get the same data. Results are split into contacts (already known)
vs others (strangers).

Mental model: the logbook IS a directory tree. Contacts are bookmarked paths,
others are the rest of the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from storage.contracts import MemberType
from storage.providers.sqlite.contact_repo import SQLiteContactRepo
from storage.providers.sqlite.member_repo import SQLiteMemberRepo


@dataclass
class DirectoryEntry:
    id: str
    name: str
    type: str  # MemberType.value
    description: str | None = None
    owner: dict[str, str] | None = None  # {id, name} for agent-type members
    is_contact: bool = False


@dataclass
class DirectoryResult:
    contacts: list[DirectoryEntry] = field(default_factory=list)
    others: list[DirectoryEntry] = field(default_factory=list)


class DirectoryService:
    """Stateless directory queries over member + contact repos."""

    def __init__(
        self,
        members: SQLiteMemberRepo,
        contacts: SQLiteContactRepo,
    ) -> None:
        self._members = members
        self._contacts = contacts

    def browse(
        self,
        requester_id: str,
        type_filter: str | None = None,
        search: str | None = None,
    ) -> DirectoryResult:
        """List all members, grouped by contact relationship.

        Args:
            requester_id: The member doing the browsing (excluded from results).
            type_filter: Optional MemberType value to filter by.
            search: Optional case-insensitive substring match on name or owner name.
        """
        all_members = self._members.list_all()

        # Type filter
        if type_filter:
            try:
                ft = MemberType(type_filter)
                all_members = [m for m in all_members if m.type == ft]
            except ValueError:
                pass  # unknown type → no filter

        result = DirectoryResult()
        needle = search.lower() if search else None

        for m in all_members:
            if m.id == requester_id:
                continue

            # Derive owner for agent-type members
            owner = self._find_owner(m) if m.type != MemberType.HUMAN else None

            # Search filter
            if needle:
                name_match = needle in m.name.lower()
                owner_match = owner is not None and needle in owner["name"].lower()
                if not name_match and not owner_match:
                    continue

            is_contact = self._contacts.exists(requester_id, m.id)

            entry = DirectoryEntry(
                id=m.id,
                name=m.name,
                type=m.type.value,
                description=m.description,
                owner=owner,
                is_contact=is_contact,
            )

            if is_contact:
                result.contacts.append(entry)
            else:
                result.others.append(entry)

        return result

    def _find_owner(self, agent_member: Any) -> dict[str, str] | None:
        """Read owner directly from member row's owner_id."""
        if not agent_member.owner_id:
            return None
        owner = self._members.get_by_id(agent_member.owner_id)
        if owner:
            return {"id": owner.id, "name": owner.name}
        return None
