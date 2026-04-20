from __future__ import annotations

import json
from collections.abc import Awaitable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import AnyUrl, TypeAdapter

from core.runtime.registry import ToolRegistry
from core.runtime.tool_result import ToolResultEnvelope
from core.tools.mcp_resources.service import McpResourceToolService


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
async def test_mcp_resource_tool_service_registers_list_and_read_tools() -> None:
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

    McpResourceToolService(
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


def test_mcp_resource_tool_service_skips_registration_without_servers() -> None:
    registry = ToolRegistry()
    McpResourceToolService(
        registry=registry,
        client_fn=lambda: None,
        server_configs_fn=lambda: {},
    )

    assert registry.get("ListMcpResources") is None
    assert registry.get("ReadMcpResource") is None


@pytest.mark.asyncio
async def test_mcp_resource_tool_service_fails_loudly_for_unknown_server() -> None:
    registry = ToolRegistry()
    client = _FakeClient({"demo": _FakeSession(resources=[], contents_by_uri={})})
    McpResourceToolService(
        registry=registry,
        client_fn=lambda: client,
        server_configs_fn=lambda: {"demo": object()},
    )

    read_entry = registry.get("ReadMcpResource")
    assert read_entry is not None

    with pytest.raises(ValueError, match='MCP server not found: "missing"'):
        await _invoke_handler(read_entry.handler, server="missing", uri="memo://alpha")


@pytest.mark.asyncio
async def test_mcp_resource_tool_service_serializes_url_like_resource_uris() -> None:
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

    McpResourceToolService(
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
