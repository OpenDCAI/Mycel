from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.core import dependencies


class _Request:
    def __init__(self, *, token: str, payload: dict, member_exists: bool = True) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                auth_service=SimpleNamespace(verify_token=lambda seen: payload if seen == token else None),
                member_repo=SimpleNamespace(get_by_id=lambda _user_id: object() if member_exists else None),
            )
        )


@pytest.mark.asyncio
async def test_get_current_user_id_still_rejects_deleted_user():
    request = _Request(token="tok-1", payload={"user_id": "ghost-user"}, member_exists=False)

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User no longer exists — please re-login"
