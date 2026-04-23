"""Standalone HTTP clients for the Stage-1 agent CLI.

These intentionally do not import from `backend.*` so the CLI can move into a
separate package/repo later without dragging server internals with it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx


class ChatHttpClient:
    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, trust_env=False)

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        with self._client() as client:
            response = client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    def _post_json(self, path: str, *, json: dict[str, Any]) -> Any:
        with self._client() as client:
            response = client.post(path, json=json)
            response.raise_for_status()
            return response.json()

    def resolve_display_user(self, social_user_id: str) -> Any | None:
        try:
            payload = self._get_json(f"/api/internal/messaging/display-users/{social_user_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return SimpleNamespace(**payload)

    def list_chats_for_user(self, user_id: str) -> list[dict[str, Any]]:
        return self._get_json("/api/internal/messaging/chats", params={"user_id": user_id})

    def find_direct_chat_id(self, actor_id: str, target_id: str) -> str | None:
        payload = self._post_json(
            "/api/internal/messaging/direct-chat-id",
            json={"actor_id": actor_id, "target_id": target_id},
        )
        return payload["chat_id"]

    def list_messages(
        self,
        chat_id: str,
        *,
        limit: int = 50,
        before: str | None = None,
        viewer_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            params["before"] = before
        if viewer_id is not None:
            params["viewer_id"] = viewer_id
        return self._get_json(f"/api/internal/messaging/chats/{chat_id}/messages", params=params)

    def list_unread(self, chat_id: str, user_id: str) -> list[dict[str, Any]]:
        return self._get_json(f"/api/internal/messaging/chats/{chat_id}/messages/unread", params={"user_id": user_id})

    def count_unread(self, chat_id: str, user_id: str) -> int:
        payload = self._get_json(f"/api/internal/messaging/chats/{chat_id}/unread-count", params={"user_id": user_id})
        return int(payload["count"])

    def mark_read(self, chat_id: str, user_id: str) -> None:
        self._post_json(f"/api/internal/messaging/chats/{chat_id}/read", json={"user_id": user_id})

    def send(
        self,
        chat_id: str,
        sender_id: str,
        content: str,
        *,
        message_type: str = "human",
        content_type: str = "text",
        mentions: list[str] | None = None,
        signal: str | None = None,
        reply_to: str | None = None,
        ai_metadata: dict[str, Any] | None = None,
        enforce_caught_up: bool = False,
    ) -> dict[str, Any]:
        return self._post_json(
            f"/api/internal/messaging/chats/{chat_id}/messages/send",
            json={
                "sender_id": sender_id,
                "content": content,
                "message_type": message_type,
                "content_type": content_type,
                "mentions": mentions,
                "signal": signal,
                "reply_to": reply_to,
                "ai_metadata": ai_metadata,
                "enforce_caught_up": enforce_caught_up,
            },
        )


class IdentityHttpClient:
    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, trust_env=False)

    def create_external_user(self, *, user_id: str, display_name: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                "/api/internal/identity/users/external",
                json={"user_id": user_id, "display_name": display_name},
            )
            response.raise_for_status()
            return response.json()

    def list_users(self, *, user_type: str) -> list[dict[str, Any]]:
        with self._client() as client:
            response = client.get("/api/internal/identity/users", params={"type": user_type})
            response.raise_for_status()
            return response.json()


class ThreadsRuntimeHttpClient:
    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, trust_env=False)

    def is_agent_actor_user(self, social_user_id: str) -> bool:
        with self._client() as client:
            response = client.get(f"/api/internal/identity/agent-actors/{social_user_id}/exists")
            response.raise_for_status()
            return bool(response.json()["exists"])


class AuthHttpClient:
    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, trust_env=False)

    def login(self, identifier: str, password: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
            response.raise_for_status()
            return response.json()

    def send_otp(self, email: str, password: str, invite_code: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                "/api/auth/send-otp",
                json={"email": email, "password": password, "invite_code": invite_code},
            )
            response.raise_for_status()
            return response.json()

    def verify_otp(self, email: str, token: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.post("/api/auth/verify-otp", json={"email": email, "token": token})
            response.raise_for_status()
            return response.json()

    def complete_register(self, temp_token: str, invite_code: str) -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                "/api/auth/complete-register",
                json={"temp_token": temp_token, "invite_code": invite_code},
            )
            response.raise_for_status()
            return response.json()


class PanelHttpClient:
    def __init__(self, *, base_url: str, auth_token: str | None, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, trust_env=False)

    def _auth_headers(self) -> dict[str, str]:
        if not self._auth_token:
            raise RuntimeError("MYCEL_AGENT_AUTH_TOKEN is required")
        return {"Authorization": f"Bearer {self._auth_token}"}

    def list_agents(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get("/api/panel/agents", headers=self._auth_headers())
            response.raise_for_status()
            return response.json()

    def create_agent(self, name: str, *, description: str = "") -> dict[str, Any]:
        with self._client() as client:
            response = client.post(
                "/api/panel/agents",
                json={"name": name, "description": description},
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            return response.json()
