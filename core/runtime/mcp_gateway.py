"""Small MCP boundary for LeonAgent."""

from __future__ import annotations

import asyncio
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


def instruction_blocks(server_configs: dict[str, Any]) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for name, cfg in server_configs.items():
        instructions = getattr(cfg, "instructions", None)
        if isinstance(instructions, str) and instructions.strip():
            blocks[name] = instructions.strip()
    return blocks


def register_mcp_tools(registry: ToolRegistry, mcp_tools: list[Any]) -> None:
    for tool in mcp_tools:
        registry.register(make_tool_entry(tool))


def register_resource_tools(
    registry: ToolRegistry,
    *,
    client_fn: Callable[[], Any],
    server_configs_fn: Callable[[], dict[str, Any]],
) -> Any:
    return _ResourceToolRegistrar(
        registry=registry,
        client_fn=client_fn,
        server_configs_fn=server_configs_fn,
    )


async def init_client_tools(
    *,
    enabled: bool,
    server_configs: dict[str, Any],
) -> tuple[Any | None, list[Any]]:
    if not enabled or not server_configs:
        return None, []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    configs = _adapter_configs(server_configs)
    try:
        client = MultiServerMCPClient(configs, tool_name_prefix=False)
        tools: list[Any] = []
        for server_name in configs:
            server_tools = await client.get_tools(server_name=server_name)
            _apply_server_prefixes(server_tools, server_name)
            tools.extend(server_tools)
        tools = _filter_allowed_tools(tools, server_configs)
        return client, tools
    except Exception as exc:
        raise RuntimeError(f"MCP initialization failed: {exc}") from exc


def make_tool_entry(tool: Any) -> ToolEntry:
    schema_model = getattr(tool, "tool_call_schema", None)
    if schema_model is not None and hasattr(schema_model, "model_json_schema"):
        parameters = schema_model.model_json_schema()
    else:
        parameters = {
            "type": "object",
            "properties": getattr(tool, "args", {}) or {},
        }

    async def mcp_handler(**kwargs: Any) -> Any:
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(kwargs)
        return await asyncio.to_thread(tool.invoke, kwargs)

    return ToolEntry(
        name=tool.name,
        mode=ToolMode.INLINE,
        schema=make_tool_schema(
            name=tool.name,
            description=getattr(tool, "description", "") or tool.name,
            properties={},
            parameter_overrides=parameters,
        ),
        handler=mcp_handler,
        source="mcp",
    )


class _ResourceToolRegistrar:
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
                    source="mcp",
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


def _adapter_configs(server_configs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}
    for name, cfg in server_configs.items():
        transport = getattr(cfg, "transport", None)
        if cfg.url:
            # @@@mcp-transport-honesty - URL-based MCP is not always streamable_http;
            # websocket/sse must stay explicit.
            config = {
                "transport": transport or "streamable_http",
                "url": cfg.url,
            }
        else:
            config = {
                "transport": transport or "stdio",
                "command": cfg.command,
                "args": cfg.args,
            }
        if cfg.env:
            config["env"] = cfg.env
        configs[name] = config
    return configs


def _apply_server_prefixes(tools: list[Any], server_name: str) -> None:
    for tool in tools:
        tool.name = f"mcp__{server_name}__{tool.name}"


def _filter_allowed_tools(tools: list[Any], server_configs: dict[str, Any]) -> list[Any]:
    if not any(cfg.allowed_tools for cfg in server_configs.values()):
        return tools
    return [tool for tool in tools if _is_tool_allowed(tool, server_configs)]


def _is_tool_allowed(tool: Any, server_configs: dict[str, Any]) -> bool:
    tool_name = tool.name
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        if len(parts) == 3:
            server_name = parts[1]
            tool_name = parts[2]
            cfg = server_configs.get(server_name)
            if cfg is None or not cfg.allowed_tools:
                return True
            return tool_name in cfg.allowed_tools

    for cfg in server_configs.values():
        if cfg.allowed_tools:
            return tool_name in cfg.allowed_tools
    return True
