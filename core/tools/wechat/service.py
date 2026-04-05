"""WeChat tool service — registers wechat_send and wechat_contacts into ToolRegistry.

Thin wrapper: actual API calls go through WeChatConnection (backend).
Tools are scoped to the agent's owner's entity_id (the human who connected WeChat).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

if TYPE_CHECKING:
    from backend.web.services.wechat_service import WeChatConnection

logger = logging.getLogger(__name__)


class WeChatToolService:
    """Registers WeChat tools for agents to interact with WeChat contacts.

    @@@lazy-connection — connection_fn is called at tool invocation time, not registration.
    This avoids import-time dependency on app.state.
    """

    def __init__(self, registry: ToolRegistry, connection_fn: Callable[[], WeChatConnection | None]) -> None:
        self._get_conn = connection_fn
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        self._register_wechat_send(registry)
        self._register_wechat_contacts(registry)

    def _register_wechat_send(self, registry: ToolRegistry) -> None:
        get_conn = self._get_conn

        async def handle(user_id: str, text: str) -> str:
            conn = get_conn()
            if not conn or not conn.connected:
                return "Error: WeChat is not connected. Ask the owner to connect via the Connections page."
            try:
                await conn.send_message(user_id, text)
                return f"Message sent to {user_id.split('@')[0]}"
            except RuntimeError as e:
                return f"Error: {e}"

        registry.register(
            ToolEntry(
                name="wechat_send",
                mode=ToolMode.INLINE,
                schema={
                    "name": "wechat_send",
                    "description": (
                        "Send a text message to a WeChat user via the connected WeChat bot.\n"
                        "Use wechat_contacts to find available user_ids.\n"
                        "The user must have messaged the bot first before you can reply.\n"
                        "Keep messages concise — WeChat is a chat app. Use plain text, no markdown."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "string",
                                "description": "WeChat user ID (format: xxx@im.wechat). Get from wechat_contacts.",
                            },
                            "text": {
                                "type": "string",
                                "description": "Plain text message to send. No markdown — WeChat won't render it.",
                            },
                        },
                        "required": ["user_id", "text"],
                    },
                },
                handler=handle,
                source="wechat",
            )
        )

    def _register_wechat_contacts(self, registry: ToolRegistry) -> None:
        get_conn = self._get_conn

        def handle() -> str:
            conn = get_conn()
            if not conn or not conn.connected:
                return "WeChat is not connected."
            contacts = conn.list_contacts()
            if not contacts:
                return "No WeChat contacts yet. Users need to message the bot first."
            lines = [f"- {c['display_name']} [user_id: {c['user_id']}]" for c in contacts]
            return "\n".join(lines)

        registry.register(
            ToolEntry(
                name="wechat_contacts",
                mode=ToolMode.INLINE,
                schema={
                    "name": "wechat_contacts",
                    "description": "List WeChat contacts who have messaged the bot. Returns user_ids for use with wechat_send.",  # noqa: E501
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
                handler=handle,
                source="wechat",
            )
        )
