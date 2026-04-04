from __future__ import annotations

from types import SimpleNamespace

import pytest

from config.schema import MCPConfig, MCPServerConfig
from core.runtime.agent import LeonAgent


@pytest.mark.asyncio
async def test_init_mcp_tools_respects_explicit_websocket_transport(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, configs, tool_name_prefix=False):
            captured["configs"] = configs

        async def get_tools(self):
            return []

        async def close(self):
            return None

    agent = LeonAgent.__new__(LeonAgent)
    agent.config = SimpleNamespace(
        mcp=MCPConfig(
            enabled=True,
            servers={
                "wsdemo": MCPServerConfig(
                    transport="websocket",
                    url="ws://example.test/mcp",
                )
            },
        )
    )
    agent.verbose = False
    agent._mcp_client = None

    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient",
        FakeClient,
    )

    await LeonAgent._init_mcp_tools(agent)

    assert captured["configs"] == {
        "wsdemo": {
            "transport": "websocket",
            "url": "ws://example.test/mcp",
        }
    }
