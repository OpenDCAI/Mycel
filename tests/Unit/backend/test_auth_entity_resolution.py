from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.core import dependencies


class _Request:
    def __init__(self, *, token: str, payload: dict, user_exists: bool = True) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                auth_service=SimpleNamespace(verify_token=lambda seen: payload if seen == token else None),
                user_repo=SimpleNamespace(get_by_id=lambda _user_id: object() if user_exists else None),
                member_repo=SimpleNamespace(
                    get_by_id=lambda _user_id: (_ for _ in ()).throw(AssertionError("member_repo should not gate auth"))
                ),
            )
        )


@pytest.mark.asyncio
async def test_get_current_user_id_still_rejects_deleted_user():
    request = _Request(token="tok-1", payload={"user_id": "ghost-user"}, user_exists=False)

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User no longer exists — please re-login"


@pytest.mark.asyncio
async def test_get_current_user_id_uses_user_repo_instead_of_member_repo():
    request = _Request(token="tok-1", payload={"user_id": "user-1"}, user_exists=True)

    assert await dependencies.get_current_user_id(request) == "user-1"
