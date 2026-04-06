from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import invite_codes as invite_codes_router


class _FakeInviteCodeRepo:
    def __init__(self) -> None:
        self.list_all_calls = 0
        self.generate_calls: list[tuple[str, int | None]] = []
        self.revoke_calls: list[str] = []
        self.is_valid_calls: list[str] = []
        self.list_all_result = [{"code": "invite-1"}]
        self.generate_result = {"code": "invite-2"}
        self.revoke_result = True
        self.is_valid_result = True
        self.list_all_error: Exception | None = None
        self.generate_error: Exception | None = None
        self.revoke_error: Exception | None = None
        self.is_valid_error: Exception | None = None

    def list_all(self):
        self.list_all_calls += 1
        if self.list_all_error is not None:
            raise self.list_all_error
        return self.list_all_result

    def generate(self, *, created_by: str, expires_days: int | None):
        self.generate_calls.append((created_by, expires_days))
        if self.generate_error is not None:
            raise self.generate_error
        return self.generate_result

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
async def test_call_invite_code_repo_returns_repo_result():
    repo = _FakeInviteCodeRepo()

    result = await invite_codes_router._call_invite_code_repo(
        _request(repo),
        "获取邀请码列表失败：",
        "list_all",
    )

    assert result == [{"code": "invite-1"}]
    assert repo.list_all_calls == 1


@pytest.mark.asyncio
async def test_call_invite_code_repo_maps_exception_to_prefixed_500():
    repo = _FakeInviteCodeRepo()
    repo.generate_error = RuntimeError("db down")

    with pytest.raises(HTTPException) as exc_info:
        await invite_codes_router._call_invite_code_repo(
            _request(repo),
            "生成邀请码失败：",
            "generate",
            created_by="user-1",
            expires_days=7,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "生成邀请码失败：db down"


@pytest.mark.asyncio
async def test_call_invite_code_repo_preserves_http_exception():
    repo = _FakeInviteCodeRepo()
    repo.is_valid_error = HTTPException(503, "邀请码仓库未初始化")

    with pytest.raises(HTTPException) as exc_info:
        await invite_codes_router._call_invite_code_repo(
            _request(repo),
            "校验邀请码失败：",
            "is_valid",
            "invite-1",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "邀请码仓库未初始化"


@pytest.mark.asyncio
async def test_list_invite_codes_uses_router_helper(monkeypatch: pytest.MonkeyPatch):
    request = _request(_FakeInviteCodeRepo())
    calls: list[tuple[object, str, str, tuple[object, ...], dict[str, object]]] = []

    async def fake_call(request_obj, error_prefix: str, method_name: str, *args: object, **kwargs: object):
        calls.append((request_obj, error_prefix, method_name, args, kwargs))
        return [{"code": "invite-1"}]

    monkeypatch.setattr(invite_codes_router, "_call_invite_code_repo", fake_call)

    result = await invite_codes_router.list_invite_codes(request=request, user_id="user-1")

    assert result == {"codes": [{"code": "invite-1"}]}
    assert calls == [
        (
            request,
            "获取邀请码列表失败：",
            "list_all",
            (),
            {},
        )
    ]


@pytest.mark.asyncio
async def test_revoke_invite_code_uses_helper_and_keeps_404(monkeypatch: pytest.MonkeyPatch):
    request = _request(_FakeInviteCodeRepo())
    calls: list[tuple[object, str, str, tuple[object, ...], dict[str, object]]] = []

    async def fake_call(request_obj, error_prefix: str, method_name: str, *args: object, **kwargs: object):
        calls.append((request_obj, error_prefix, method_name, args, kwargs))
        return False

    monkeypatch.setattr(invite_codes_router, "_call_invite_code_repo", fake_call)

    with pytest.raises(HTTPException) as exc_info:
        await invite_codes_router.revoke_invite_code("invite-1", request=request, user_id="user-1")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "邀请码不存在"
    assert calls == [
        (
            request,
            "吊销邀请码失败：",
            "revoke",
            ("invite-1",),
            {},
        )
    ]
