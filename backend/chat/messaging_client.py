"""HTTP-backed client for chat-owned internal messaging routes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx


class HttpMessagingServiceClient:
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

    def find_or_create_chat(self, user_ids: list[str], title: str | None = None) -> dict[str, Any]:
        return self._post_json(
            "/api/internal/messaging/chats/find-or-create",
            json={"user_ids": user_ids, "title": title},
        )

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

    def list_messages_by_time_range(
        self,
        chat_id: str,
        *,
        after: str | None = None,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        return self._get_json(f"/api/internal/messaging/chats/{chat_id}/messages/by-time-range", params=params)

    def list_unread(self, chat_id: str, user_id: str) -> list[dict[str, Any]]:
        return self._get_json(f"/api/internal/messaging/chats/{chat_id}/messages/unread", params={"user_id": user_id})

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

    def mark_read(self, chat_id: str, user_id: str) -> None:
        self._post_json(f"/api/internal/messaging/chats/{chat_id}/read", json={"user_id": user_id})

    def is_chat_member(self, chat_id: str, user_id: str) -> bool:
        payload = self._get_json(f"/api/internal/messaging/chats/{chat_id}/members/{user_id}/is-member")
        return bool(payload["is_member"])

    def count_unread(self, chat_id: str, user_id: str) -> int:
        payload = self._get_json(f"/api/internal/messaging/chats/{chat_id}/unread-count", params={"user_id": user_id})
        return int(payload["count"])

    def search_messages(self, query: str, *, chat_id: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": query}
        if chat_id is not None:
            params["chat_id"] = chat_id
        return self._get_json("/api/internal/messaging/messages/search", params=params)


def build_http_messaging_service_client(*, base_url: str, timeout: float = 10.0) -> HttpMessagingServiceClient:
    return HttpMessagingServiceClient(base_url=base_url, timeout=timeout)
