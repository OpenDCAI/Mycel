from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import invite_codes as invite_codes_router


class _FakeInviteCodeRepo:
    def __init__(self) -> None:
        self.generate_calls: list[tuple[str, int | None]] = []
        self.revoke_calls: list[str] = []
        self.is_valid_calls: list[str] = []
        self.generate_result = {"code": "invite-2"}
        self.list_all_result: list[dict] = []
        self.revoke_result = True
        self.is_valid_result = True
        self.generate_error: Exception | None = None
        self.revoke_error: Exception | None = None
        self.is_valid_error: Exception | None = None

    def generate(self, *, created_by: str, expires_days: int | None):
        self.generate_calls.append((created_by, expires_days))
        if self.generate_error is not None:
            raise self.generate_error
        return self.generate_result

    def list_all(self):
        return self.list_all_result

    def revoke(self, code: str):
        self.revoke_calls.append(code)
        if self.revoke_error is not None:
            raise self.revoke_error
        return self.revoke_result

    def is_valid(self, code: str):
        self.is_valid_calls.append(code)
        if self.is_valid_error is not None:
            raise self.is_valid_error
        return self.is_valid_result


def _request(repo: _FakeInviteCodeRepo):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(_supabase_client=object(), invite_code_repo=repo)))


@pytest.mark.asyncio
async def test_call_invite_code_repo_maps_exception_to_prefixed_500():
    repo = _FakeInviteCodeRepo()
    repo.generate_error = RuntimeError("db down")

    with pytest.raises(HTTPException) as exc_info:
        await invite_codes_router._call_invite_code_repo(
            "生成邀请码失败：",
            lambda: repo.generate(created_by="user-1", expires_days=7),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "生成邀请码失败：db down"


@pytest.mark.asyncio
async def test_call_invite_code_repo_preserves_http_exception():
    repo = _FakeInviteCodeRepo()
    repo.is_valid_error = HTTPException(503, "邀请码仓库未初始化")

    with pytest.raises(HTTPException) as exc_info:
        await invite_codes_router._call_invite_code_repo(
            "校验邀请码失败：",
            lambda: repo.is_valid("invite-1"),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "邀请码仓库未初始化"


@pytest.mark.asyncio
async def test_revoke_invite_code_raises_404_when_repo_reports_missing():
    repo = _FakeInviteCodeRepo()
    repo.revoke_result = False
    request = _request(repo)

    with pytest.raises(HTTPException) as exc_info:
        await invite_codes_router.revoke_invite_code("invite-1", request=request, user_id="user-1")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "邀请码不存在"
    assert repo.revoke_calls == ["invite-1"]


@pytest.mark.asyncio
async def test_list_invite_codes_returns_app_contract_from_repo_rows():
    repo = _FakeInviteCodeRepo()
    repo.list_all_result = [
        {
            "code": "USED",
            "used_by": "user-2",
            "used_at": "2026-04-12T00:01:00Z",
            "expires_at": None,
            "created_at": "2026-04-12T00:00:00Z",
        },
        {
            "code": "OPEN",
            "used_by": None,
            "used_at": None,
            "expires_at": "2026-04-19T00:00:00Z",
            "created_at": "2026-04-12T00:00:00Z",
        },
    ]

    result = await invite_codes_router.list_invite_codes(request=_request(repo), user_id="user-1")

    assert result == {
        "codes": [
            {
                "code": "USED",
                "used": True,
                "used_by": "user-2",
                "used_at": "2026-04-12T00:01:00Z",
                "expires_at": None,
                "created_at": "2026-04-12T00:00:00Z",
            },
            {
                "code": "OPEN",
                "used": False,
                "used_by": None,
                "used_at": None,
                "expires_at": "2026-04-19T00:00:00Z",
                "created_at": "2026-04-12T00:00:00Z",
            },
        ]
    }


@pytest.mark.asyncio
async def test_generate_invite_code_returns_app_contract_from_repo_row():
    repo = _FakeInviteCodeRepo()
    repo.generate_result = {
        "code": "NEW",
        "used_by": None,
        "used_at": None,
        "expires_at": "2026-04-19T00:00:00Z",
        "created_at": "2026-04-12T00:00:00Z",
    }

    result = await invite_codes_router.generate_invite_code(
        invite_codes_router.GenerateInviteCodeRequest(expires_days=7),
        request=_request(repo),
        user_id="user-1",
    )

    assert result == {
        "code": "NEW",
        "used": False,
        "used_by": None,
        "used_at": None,
        "expires_at": "2026-04-19T00:00:00Z",
        "created_at": "2026-04-12T00:00:00Z",
    }
    assert repo.generate_calls == [("user-1", 7)]
