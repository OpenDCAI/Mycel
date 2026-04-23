from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.api.http import app_router as chat_app_router
from backend.chat.api.http.dependencies import get_app
from storage.contracts import UserRow, UserType


class _FakeUserRepo:
    def __init__(self) -> None:
        self.rows: dict[str, UserRow] = {}

    def create(self, row: UserRow) -> None:
        self.rows[row.id] = row

    def get_by_id(self, user_id: str):
        return self.rows.get(user_id)

    def list_by_type(self, user_type: str):
        return [row for row in self.rows.values() if row.type.value == user_type]


def _app_state() -> SimpleNamespace:
    user_repo = _FakeUserRepo()
    return SimpleNamespace(
        state=SimpleNamespace(
            auth_runtime_state=SimpleNamespace(user_directory=user_repo),
            user_repo=user_repo,
            chat_runtime_state=SimpleNamespace(
                messaging_service=object(),
                relationship_service=object(),
                contact_repo=object(),
                chat_repo=object(),
                chat_event_bus=object(),
                typing_tracker=object(),
                hire_conversation_reader=object(),
                agent_actor_lookup=object(),
            ),
            threads_runtime_state=SimpleNamespace(activity_reader=object()),
            thread_last_active={},
            thread_repo=object(),
        )
    )


def test_internal_identity_router_creates_external_user() -> None:
    app_state = _app_state()
    app = FastAPI()
    app.include_router(chat_app_router.router)
    app.dependency_overrides[get_app] = lambda: app_state

    with TestClient(app) as client:
        response = client.post(
            "/api/internal/identity/users/external",
            json={"user_id": "external-user-1", "display_name": "Codex External"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": "external-user-1",
        "type": "external",
        "display_name": "Codex External",
        "owner_user_id": None,
        "agent_config_id": None,
    }


def test_internal_identity_router_lists_external_users() -> None:
    app_state = _app_state()
    app_state.state.user_repo.create(
        UserRow(id="external-user-1", type=UserType.EXTERNAL, display_name="Codex External", created_at=1.0)
    )
    app = FastAPI()
    app.include_router(chat_app_router.router)
    app.dependency_overrides[get_app] = lambda: app_state

    with TestClient(app) as client:
        response = client.get("/api/internal/identity/users", params={"type": "external"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "external-user-1",
            "type": "external",
            "display_name": "Codex External",
            "owner_user_id": None,
            "agent_config_id": None,
        }
    ]
