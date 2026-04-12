from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.routers import sandbox as sandbox_router


def test_sandbox_router_does_not_expose_local_folder_picker() -> None:
    paths = {route.path for route in sandbox_router.router.routes}

    assert "/api/sandbox/pick-folder" not in paths


@pytest.mark.asyncio
async def test_list_my_leases_uses_user_repo_not_member_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_list_user_leases(user_id: str, *, thread_repo=None, user_repo=None) -> list[dict[str, object]]:
        seen.update(
            {
                "user_id": user_id,
                "thread_repo": thread_repo,
                "user_repo": user_repo,
            }
        )
        return [{"lease_id": "lease-1"}]

    thread_repo = SimpleNamespace()
    user_repo = SimpleNamespace()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                thread_repo=thread_repo,
                user_repo=user_repo,
                member_repo=SimpleNamespace(
                    get_by_id=lambda _member_id: (_ for _ in ()).throw(AssertionError("member_repo should not back sandbox lease shell"))
                ),
            )
        )
    )
    monkeypatch.setattr(sandbox_router.sandbox_service, "list_user_leases", fake_list_user_leases)

    result = await sandbox_router.list_my_leases(user_id="owner-1", request=request)

    assert result == {"leases": [{"lease_id": "lease-1"}]}
    assert seen == {
        "user_id": "owner-1",
        "thread_repo": thread_repo,
        "user_repo": user_repo,
    }
