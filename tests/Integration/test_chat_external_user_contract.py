from __future__ import annotations

from types import SimpleNamespace

from backend.chat.api.http import chats_router
from storage.contracts import UserRow, UserType


def _user_directory(rows: dict[str, UserRow]):
    return SimpleNamespace(get_by_id=lambda user_id: rows.get(user_id))


def test_validate_chat_participant_ids_accepts_external_user() -> None:
    rows = {
        'human-1': UserRow(id='human-1', display_name='Owner', type=UserType.HUMAN, created_at=1.0),
        'external-1': UserRow(id='external-1', display_name='Codex External', type=UserType.EXTERNAL, created_at=1.0),
    }

    result = chats_router._validate_chat_participant_ids(
        _user_directory(rows),
        SimpleNamespace(get_by_user_id=lambda _user_id: None),
        participant_ids=['human-1', 'external-1'],
        requester_user_id='human-1',
    )

    assert result == ['human-1', 'external-1']
