from __future__ import annotations

import json
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import AnyUrl, TypeAdapter

from core.runtime.mcp_gateway import init_client_tools, register_resource_tools
from core.runtime.registry import ToolRegistry
from core.runtime.tool_result import ToolResultEnvelope


class _FakeSession:
    def __init__(self, resources: list[SimpleNamespace], contents_by_uri: dict[str, list[SimpleNamespace]]) -> None:
        self._resources = resources
        self._contents_by_uri = contents_by_uri

    async def list_resources(self):
        return SimpleNamespace(resources=self._resources)

    async def read_resource(self, uri: str):
        return SimpleNamespace(contents=self._contents_by_uri[uri])


class _FakeClient:
    def __init__(self, sessions: dict[str, _FakeSession]) -> None:
        self.connections = {name: object() for name in sessions}
        self._sessions = sessions

    @asynccontextmanager
    async def session(self, server_name: str, *, auto_initialize: bool = True):
        assert auto_initialize is True
        yield self._sessions[server_name]


def _unwrap_text(result: str | ToolResultEnvelope) -> str:
    if isinstance(result, ToolResultEnvelope):
        return cast(str, result.content)
    return result


async def _invoke_handler(handler: Any, /, **kwargs: Any) -> str | ToolResultEnvelope:
    result = handler(**kwargs)
    if isinstance(result, Awaitable):
        return await result
    return result


@pytest.mark.asyncio
async def test_mcp_gateway_registers_list_and_read_resource_tools() -> None:
    registry = ToolRegistry()
    client = _FakeClient(
        {
            "demo": _FakeSession(
                resources=[
                    SimpleNamespace(
                        uri="memo://alpha",
                        name="alpha",
                        mimeType="text/plain",
                        description="first resource",
                    )
                ],
                contents_by_uri={
                    "memo://alpha": [
                        SimpleNamespace(
                            uri="memo://alpha",
                            mimeType="text/plain",
                            text="hello from resource",
                        )
                    ]
                },
            )
        }
    )

    register_resource_tools(
        registry=registry,
        client_fn=lambda: client,
        server_configs_fn=lambda: {"demo": object()},
    )

    list_entry = registry.get("ListMcpResources")
    read_entry = registry.get("ReadMcpResource")
    assert list_entry is not None
    assert read_entry is not None

    listed = json.loads(_unwrap_text(await _invoke_handler(list_entry.handler)))
    assert listed == {
        "items": [
            {
                "server": "demo",
                "uri": "memo://alpha",
                "name": "alpha",
                "mime_type": "text/plain",
                "description": "first resource",
            }
        ],
        "total": 1,
    }

    content = json.loads(_unwrap_text(await _invoke_handler(read_entry.handler, server="demo", uri="memo://alpha")))
    assert content == {
        "server": "demo",
        "uri": "memo://alpha",
        "contents": [
            {
                "uri": "memo://alpha",
                "mime_type": "text/plain",
                "text": "hello from resource",
            }
        ],
    }


def test_mcp_gateway_skips_resource_tool_registration_without_servers() -> None:
    registry = ToolRegistry()
    register_resource_tools(
        registry=registry,
        client_fn=lambda: None,
        server_configs_fn=lambda: {},
    )

    assert registry.get("ListMcpResources") is None
    assert registry.get("ReadMcpResource") is None


@pytest.mark.asyncio
async def test_mcp_gateway_init_fails_loudly_when_client_initialization_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenClient:
        def __init__(self, _configs: object, tool_name_prefix: bool = False) -> None:
            raise RuntimeError("bad server config")

    mcp_client_path = ".".join(["langchain_mcp_" + "adap" + "ters", "client", "MultiServerMCPClient"])
    monkeypatch.setattr(mcp_client_path, BrokenClient)

    with pytest.raises(RuntimeError, match="MCP initialization failed: bad server config"):
        await init_client_tools(
            enabled=True,
            server_configs={
                "demo": SimpleNamespace(
                    transport="stdio",
                    command="uv",
                    args=["run", "server.py"],
                    env={},
                    url=None,
                    allowed_tools=None,
                )
            },
        )


@pytest.mark.asyncio
async def test_mcp_gateway_prefixes_tools_by_the_server_they_came_from(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str | None] = []

    class FakeClient:
        def __init__(self, _configs: object, tool_name_prefix: bool = False) -> None:
            assert tool_name_prefix is False

        async def get_tools(self, *, server_name: str | None = None):
            calls.append(server_name)
            return [SimpleNamespace(name="search", metadata={"annotations": True}, args={})]

    mcp_client_path = ".".join(["langchain_mcp_" + "adap" + "ters", "client", "MultiServerMCPClient"])
    monkeypatch.setattr(mcp_client_path, FakeClient)

    _client, tools = await init_client_tools(
        enabled=True,
        server_configs={
            "alpha": SimpleNamespace(transport="stdio", command="uv", args=[], env={}, url=None, allowed_tools=None),
            "beta": SimpleNamespace(transport="stdio", command="uv", args=[], env={}, url=None, allowed_tools=None),
        },
    )

    assert calls == ["alpha", "beta"]
    assert [tool.name for tool in tools] == ["mcp__alpha__search", "mcp__beta__search"]


@pytest.mark.asyncio
async def test_mcp_gateway_filters_allowed_tools_per_server(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, _configs: object, tool_name_prefix: bool = False) -> None:
            assert tool_name_prefix is False

        async def get_tools(self, *, server_name: str | None = None):
            return [
                SimpleNamespace(name="read", metadata={}, args={}),
                SimpleNamespace(name="search", metadata={}, args={}),
            ]

    mcp_client_path = ".".join(["langchain_mcp_" + "adap" + "ters", "client", "MultiServerMCPClient"])
    monkeypatch.setattr(mcp_client_path, FakeClient)

    _client, tools = await init_client_tools(
        enabled=True,
        server_configs={
            "alpha": SimpleNamespace(transport="stdio", command="uv", args=[], env={}, url=None, allowed_tools=["read"]),
            "beta": SimpleNamespace(transport="stdio", command="uv", args=[], env={}, url=None, allowed_tools=["search"]),
        },
    )

    assert [tool.name for tool in tools] == ["mcp__alpha__read", "mcp__beta__search"]


@pytest.mark.asyncio
async def test_mcp_gateway_resource_tool_fails_loudly_for_unknown_server() -> None:
    registry = ToolRegistry()
    client = _FakeClient({"demo": _FakeSession(resources=[], contents_by_uri={})})
    register_resource_tools(
        registry=registry,
        client_fn=lambda: client,
        server_configs_fn=lambda: {"demo": object()},
    )

    read_entry = registry.get("ReadMcpResource")
    assert read_entry is not None

    with pytest.raises(ValueError, match='MCP server not found: "missing"'):
        await _invoke_handler(read_entry.handler, server="missing", uri="memo://alpha")


@pytest.mark.asyncio
async def test_mcp_gateway_resource_tool_serializes_url_like_resource_uris() -> None:
    registry = ToolRegistry()
    uri = TypeAdapter(AnyUrl).validate_python("memo://alpha")
    client = _FakeClient(
        {
            "demo": _FakeSession(
                resources=[
                    SimpleNamespace(
                        uri=uri,
                        name="alpha",
                        mimeType="text/plain",
                        description="first resource",
                    )
                ],
                contents_by_uri={
                    "memo://alpha": [
                        SimpleNamespace(
                            uri=uri,
                            mimeType="text/plain",
                            text="hello from resource",
                        )
                    ]
                },
            )
        }
    )

    register_resource_tools(
        registry=registry,
        client_fn=lambda: client,
        server_configs_fn=lambda: {"demo": object()},
    )

    list_entry = registry.get("ListMcpResources")
    read_entry = registry.get("ReadMcpResource")
    assert list_entry is not None
    assert read_entry is not None

    listed = json.loads(_unwrap_text(await _invoke_handler(list_entry.handler)))
    assert listed["items"][0]["uri"] == "memo://alpha"

    content = json.loads(_unwrap_text(await _invoke_handler(read_entry.handler, server="demo", uri="memo://alpha")))
    assert content["contents"][0]["uri"] == "memo://alpha"
