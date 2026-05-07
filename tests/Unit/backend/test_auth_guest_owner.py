from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import jwt
import pytest

from backend.identity.auth.service import AuthService
from storage.contracts import UserType


def test_create_guest_owner_token_creates_restricted_human_without_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret-1")
    monkeypatch.setattr("backend.identity.auth.service.uuid4", lambda: UUID("12345678-1234-5678-1234-567812345678"))
    created_rows: list[Any] = []
    user_repo = SimpleNamespace(
        get_by_id=lambda _user_id: None,
        create=lambda row: created_rows.append(row),
    )
    service = AuthService(
        users=cast(Any, user_repo),
        agent_configs=SimpleNamespace(save_agent_config=lambda _config: pytest.fail("guest must not create managed agents")),
        contact_repo=SimpleNamespace(upsert=lambda _row: pytest.fail("guest must not seed contacts")),
        recipe_repo=SimpleNamespace(upsert=lambda **_payload: pytest.fail("guest must not seed recipes")),
    )

    result = service.create_guest_owner_token(display_name="Guest Runner")

    assert len(created_rows) == 1
    assert created_rows[0].id == "guest-12345678-1234-5678-1234-567812345678"
    assert created_rows[0].type is UserType.HUMAN
    assert created_rows[0].is_guest is True
    assert created_rows[0].display_name == "Guest Runner"
    assert created_rows[0].email is None
    assert created_rows[0].mycel_id is None
    decoded = jwt.decode(result["token"], "secret-1", algorithms=["HS256"], options={"verify_aud": False})
    assert decoded["sub"] == "guest-12345678-1234-5678-1234-567812345678"
    assert decoded["mycel_is_guest"] is True
    assert service.verify_token(result["token"]) == {"user_id": "guest-12345678-1234-5678-1234-567812345678"}
    assert result["user"] == {
        "id": "guest-12345678-1234-5678-1234-567812345678",
        "name": "Guest Runner",
        "type": "human",
        "is_guest": True,
        "email": None,
        "mycel_id": None,
        "avatar": None,
    }
