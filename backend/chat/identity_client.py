"""HTTP-backed client for chat-owned internal identity routes."""

from __future__ import annotations

from typing import Any

import httpx


class HttpIdentityClient:
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


def build_http_identity_client(*, base_url: str, timeout: float = 10.0) -> HttpIdentityClient:
    return HttpIdentityClient(base_url=base_url, timeout=timeout)
