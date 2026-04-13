"""Expose MCP resource discovery and reading as agent-callable deferred tools."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema

LIST_MCP_RESOURCES_SCHEMA = make_tool_schema(
    name="ListMcpResources",
    description="List MCP resources exposed by connected MCP servers.",
    properties={
        "server": {
            "type": "string",
            "description": "Optional MCP server name to filter by.",
            "minLength": 1,
        }
    },
)

READ_MCP_RESOURCE_SCHEMA = make_tool_schema(
    name="ReadMcpResource",
    description="Read a specific MCP resource by server name and URI.",
    properties={
        "server": {
            "type": "string",
            "description": "MCP server name.",
            "minLength": 1,
        },
        "uri": {
            "type": "string",
            "description": "Resource URI to read.",
            "minLength": 1,
        },
    },
    required=["server", "uri"],
)


class McpResourceToolService:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        client_fn: Callable[[], Any | None],
        server_configs_fn: Callable[[], dict[str, Any]],
    ) -> None:
        self._client_fn = client_fn
        self._server_configs_fn = server_configs_fn
        if not self._server_configs_fn():
            return
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        for name, schema, handler in [
            ("ListMcpResources", LIST_MCP_RESOURCES_SCHEMA, self._list_resources),
            ("ReadMcpResource", READ_MCP_RESOURCE_SCHEMA, self._read_resource),
        ]:
            registry.register(
                ToolEntry(
                    name=name,
                    mode=ToolMode.DEFERRED,
                    schema=schema,
                    handler=handler,
                    source="McpResourceToolService",
                    is_concurrency_safe=True,
                    is_read_only=True,
                )
            )

    def _get_client(self) -> Any:
        client = self._client_fn()
        if client is None:
            raise ValueError("MCP client is not initialized")
        return client

    def _available_servers(self) -> list[str]:
        return list(self._server_configs_fn().keys())

    @staticmethod
    def _stringify_uri(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    async def _list_resources(self, server: str | None = None) -> str:
        client = self._get_client()
        server_names = [server] if server else self._available_servers()
        if server and server not in self._available_servers():
            raise ValueError(f'MCP server not found: "{server}"')

        items: list[dict[str, Any]] = []
        for server_name in server_names:
            async with client.session(server_name) as session:
                result = await session.list_resources()
                for resource in result.resources:
                    items.append(
                        {
                            "server": server_name,
                            "uri": self._stringify_uri(resource.uri),
                            "name": getattr(resource, "name", self._stringify_uri(resource.uri)),
                            "mime_type": getattr(resource, "mimeType", None),
                            "description": getattr(resource, "description", None),
                        }
                    )
        return json.dumps({"items": items, "total": len(items)}, ensure_ascii=False, indent=2)

    async def _read_resource(self, *, server: str, uri: str) -> str:
        client = self._get_client()
        if server not in self._available_servers():
            raise ValueError(f'MCP server not found: "{server}"')

        async with client.session(server) as session:
            result = await session.read_resource(uri)

        contents: list[dict[str, Any]] = []
        for content in result.contents:
            if hasattr(content, "text"):
                contents.append(
                    {
                        "uri": self._stringify_uri(content.uri),
                        "mime_type": getattr(content, "mimeType", None),
                        "text": content.text,
                    }
                )
                continue
            if hasattr(content, "blob"):
                blob_size = len(base64.b64decode(content.blob))
                contents.append(
                    {
                        "uri": self._stringify_uri(content.uri),
                        "mime_type": getattr(content, "mimeType", None),
                        "text": f"Binary MCP resource omitted from context ({blob_size} bytes).",
                    }
                )
                continue
            contents.append(
                {
                    "uri": self._stringify_uri(getattr(content, "uri", uri)),
                    "mime_type": getattr(content, "mimeType", None),
                }
            )

        return json.dumps(
            {
                "server": server,
                "uri": uri,
                "contents": contents,
            },
            ensure_ascii=False,
            indent=2,
        )
