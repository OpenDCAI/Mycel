"""Thin Stage-1 CLI client composed from existing HTTP clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AgentCliConfig
from .http import AuthHttpClient, ChatHttpClient, IdentityHttpClient, PanelHttpClient, ThreadsRuntimeHttpClient


@dataclass(frozen=True)
class AgentCliClient:
    messaging: Any
    identity: Any
    runtime_read: Any
    auth: Any
    panel: Any
    agent_user_id: str | None

    @classmethod
    def from_config(cls, config: AgentCliConfig) -> AgentCliClient:
        return cls(
            messaging=ChatHttpClient(base_url=config.chat_base_url),
            identity=IdentityHttpClient(base_url=config.chat_base_url),
            runtime_read=ThreadsRuntimeHttpClient(base_url=config.threads_base_url),
            auth=AuthHttpClient(base_url=config.app_base_url),
            panel=PanelHttpClient(base_url=config.app_base_url, auth_token=config.auth_token),
            agent_user_id=config.agent_user_id,
        )

    def whoami(self) -> dict[str, Any]:
        user = self.messaging.resolve_display_user(self.agent_user_id)
        if user is None:
            raise RuntimeError(f"agent user not found: {self.agent_user_id}")
        return {
            "agent_user_id": self.agent_user_id,
            "display_name": user.display_name,
            "type": getattr(user, "type", None),
            "is_agent_actor": bool(self.runtime_read.is_agent_actor_user(self.agent_user_id)),
        }

    def list_chats(self) -> list[dict[str, Any]]:
        return self.messaging.list_chats_for_user(self.agent_user_id)

    def list_messages(self, chat_id: str, *, limit: int = 50, before: str | None = None) -> list[dict[str, Any]]:
        return self.messaging.list_messages(chat_id, limit=limit, before=before, viewer_id=self.agent_user_id)

    def list_unread(self, chat_id: str) -> list[dict[str, Any]]:
        return self.messaging.list_unread(chat_id, self.agent_user_id)

    def count_unread(self, chat_id: str) -> int:
        return self.messaging.count_unread(chat_id, self.agent_user_id)

    def mark_read(self, chat_id: str) -> dict[str, Any]:
        self.messaging.mark_read(chat_id, self.agent_user_id)
        return {"status": "ok", "chat_id": chat_id, "agent_user_id": self.agent_user_id}

    def send(
        self,
        chat_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        mentions: list[str] | None = None,
        signal: str | None = None,
        enforce_caught_up: bool = True,
    ) -> dict[str, Any]:
        return self.messaging.send(
            chat_id,
            self.agent_user_id,
            content,
            reply_to=reply_to,
            mentions=mentions,
            signal=signal,
            enforce_caught_up=enforce_caught_up,
        )

    def direct(self, target_id: str) -> dict[str, Any]:
        chat_id = self.messaging.find_direct_chat_id(self.agent_user_id, target_id)
        return {"chat_id": chat_id, "agent_user_id": self.agent_user_id, "target_id": target_id}

    def create_external_user(self, *, user_id: str, display_name: str) -> dict[str, Any]:
        return self.identity.create_external_user(user_id=user_id, display_name=display_name)

    def list_external_users(self) -> list[dict[str, Any]]:
        return self.identity.list_users(user_type="external")

    def login(self, identifier: str, password: str) -> dict[str, Any]:
        return self.auth.login(identifier, password)

    def list_agents(self) -> dict[str, Any]:
        return self.panel.list_agents()

    def create_agent(self, name: str, *, description: str = "") -> dict[str, Any]:
        return self.panel.create_agent(name, description=description)
