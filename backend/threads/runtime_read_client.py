"""HTTP-backed client for threads-owned internal runtime reads."""

from __future__ import annotations

import httpx

from protocols.runtime_read import AgentThreadActivity, HireConversation


class HttpThreadRuntimeReadClient:
    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout, trust_env=False)

    def _async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout, trust_env=False)

    def list_active_threads_for_agent(self, agent_user_id: str) -> list[AgentThreadActivity]:
        with self._client() as client:
            response = client.get("/api/internal/thread-runtime/activities", params={"agent_user_id": agent_user_id})
            response.raise_for_status()
            return [AgentThreadActivity(**item) for item in response.json()]

    async def list_hire_conversations_for_user(self, user_id: str) -> list[HireConversation]:
        async with self._async_client() as client:
            response = await client.get("/api/internal/thread-runtime/conversations/hire", params={"user_id": user_id})
            response.raise_for_status()
            return [HireConversation(**item) for item in response.json()]

    def is_agent_actor_user(self, social_user_id: str) -> bool:
        with self._client() as client:
            response = client.get(f"/api/internal/identity/agent-actors/{social_user_id}/exists")
            response.raise_for_status()
            return bool(response.json()["exists"])


def build_http_thread_runtime_read_client(*, base_url: str, timeout: float = 10.0) -> HttpThreadRuntimeReadClient:
    return HttpThreadRuntimeReadClient(base_url=base_url, timeout=timeout)
