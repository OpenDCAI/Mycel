from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import resources as resources_router


@pytest.mark.asyncio
async def test_list_user_resource_providers_or_500_returns_projection_result():
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    app = object()

    def fake_list_user_resource_providers(*args: object, **kwargs: object):
        calls.append((args, kwargs))
        return {"summary": {"total_providers": 1}, "providers": []}

    result = await resources_router._list_user_resource_providers_or_500(
        fake_list_user_resource_providers,
        app,
        "user-1",
    )

    assert result == {"summary": {"total_providers": 1}, "providers": []}
    assert calls == [((app, "user-1"), {})]


@pytest.mark.asyncio
async def test_list_user_resource_providers_or_500_maps_runtime_error_to_500():
    def fake_list_user_resource_providers(*_args: object, **_kwargs: object):
        raise RuntimeError("provider unavailable")

    with pytest.raises(HTTPException) as exc_info:
        await resources_router._list_user_resource_providers_or_500(
            fake_list_user_resource_providers,
            object(),
            "user-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "provider unavailable"


@pytest.mark.asyncio
async def test_resources_overview_uses_router_shell(monkeypatch: pytest.MonkeyPatch):
    request = SimpleNamespace(app=object())
    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def fake_list_or_500(method, *args: object, **kwargs: object):
        calls.append((method, args, kwargs))
        return {"summary": {"total_providers": 2}, "providers": [{"id": "daytona"}]}

    monkeypatch.setattr(resources_router, "_list_user_resource_providers_or_500", fake_list_or_500)

    result = await resources_router.resources_overview(user_id="user-1", request=request)

    assert result == {"summary": {"total_providers": 2}, "providers": [{"id": "daytona"}]}
    assert calls == [
        (
            resources_router.resource_projection_service.list_user_resource_providers,
            (request.app, "user-1"),
            {},
        )
    ]
