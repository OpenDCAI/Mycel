"""Tests for scoped thread listing API."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.routers import threads


class FakeAuthService:
    def verify_token(self, token: str):
        if token == "token-user-1":
            return {"user_id": "user-1", "entity_id": "entity-user-1"}
        if token == "token-user-2":
            return {"user_id": "user-2", "entity_id": "entity-user-2"}
        raise ValueError("Invalid token")


class FakeThreadRepo:
    def list_by_owner_user_id(self, user_id: str):
        rows = {
            "user-1": [
                {
                    "id": "thread-1",
                    "sandbox_type": "local",
                    "member_name": "Agent A",
                    "member_id": "member-a",
                    "entity_name": "Agent A",
                    "branch_index": 0,
                    "is_main": 1,
                    "member_avatar": None,
                },
            ],
            "user-2": [
                {
                    "id": "thread-2",
                    "sandbox_type": "local",
                    "member_name": "Agent B",
                    "member_id": "member-b",
                    "entity_name": "Agent B",
                    "branch_index": 0,
                    "is_main": 1,
                    "member_avatar": None,
                },
            ],
        }
        return rows.get(user_id, [])


def _make_client():
    app = FastAPI()
    app.state.auth_service = FakeAuthService()
    app.state.thread_repo = FakeThreadRepo()
    app.state.agent_pool = {}
    app.state.thread_last_active = {}
    app.include_router(threads.router)
    return TestClient(app)


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer token-{user_id}"}


def test_list_threads_scope_owned():
    client = _make_client()

    response = client.get("/api/threads?scope=owned", headers=_auth_headers("user-1"))

    assert response.status_code == 200
    assert [row["thread_id"] for row in response.json()["threads"]] == ["thread-1"]


def test_list_threads_scope_visible_matches_owned_for_now():
    client = _make_client()

    owned = client.get("/api/threads?scope=owned", headers=_auth_headers("user-1"))
    visible = client.get("/api/threads?scope=visible", headers=_auth_headers("user-1"))

    assert visible.status_code == 200
    assert visible.json() == owned.json()


def test_list_threads_scope_rejects_invalid_value():
    client = _make_client()

    response = client.get("/api/threads?scope=nope", headers=_auth_headers("user-1"))

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid thread scope"
