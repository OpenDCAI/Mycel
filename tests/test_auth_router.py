from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import auth as auth_router


@pytest.mark.asyncio
async def test_register_fails_loudly_when_backend_auth_bypass_is_active(monkeypatch):
    monkeypatch.setattr(auth_router, "is_dev_skip_auth_enabled", lambda: True)
    app = SimpleNamespace(state=SimpleNamespace(auth_service=None))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.register(auth_router.AuthRequest(username="fresh", password="pass1234"), app)

    assert exc_info.value.status_code == 409
    assert "LEON_DEV_SKIP_AUTH" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_login_fails_loudly_when_backend_auth_bypass_is_active(monkeypatch):
    monkeypatch.setattr(auth_router, "is_dev_skip_auth_enabled", lambda: True)
    app = SimpleNamespace(state=SimpleNamespace(auth_service=None))

    with pytest.raises(HTTPException) as exc_info:
        await auth_router.login(auth_router.AuthRequest(username="fresh", password="pass1234"), app)

    assert exc_info.value.status_code == 409
    assert "LEON_DEV_SKIP_AUTH" in str(exc_info.value.detail)
