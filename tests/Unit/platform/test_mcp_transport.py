from __future__ import annotations

import pytest

from config.agent_config_types import McpServerConfig
from config.agent_config_types import ResolvedAgentConfig
from config.schema import LeonSettings
from core.runtime.agent import LeonAgent


def _agent_with_mcp(*servers: McpServerConfig) -> LeonAgent:
    agent = LeonAgent.__new__(LeonAgent)
    agent.config = LeonSettings()
    agent._resolved_agent_config = ResolvedAgentConfig(
        id="cfg-1",
        name="Agent",
        mcp_servers=list(servers),
    )
    agent._mcp_client = None
    return agent


@pytest.mark.asyncio
async def test_init_mcp_tools_respects_explicit_websocket_transport(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, configs, tool_name_prefix=False):
            captured["configs"] = configs

        async def get_tools(self, *, server_name: str | None = None):
            return []

        async def close(self):
            return None

    agent = _agent_with_mcp(
        McpServerConfig(
            name="wsdemo",
            transport="websocket",
            url="ws://example.test/mcp",
        )
    )

    mcp_client_path = ".".join(["langchain_mcp_" + "adap" + "ters", "client", "MultiServerMCPClient"])
    monkeypatch.setattr(mcp_client_path, FakeClient)

    await LeonAgent._init_mcp_tools(agent)

    assert captured["configs"] == {
        "wsdemo": {
            "transport": "websocket",
            "url": "ws://example.test/mcp",
        }
    }


@pytest.mark.asyncio
async def test_resolved_agent_config_controls_mcp_enablement(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_init_client_tools(*, enabled: bool, server_configs: dict[str, object]):
        captured["enabled"] = enabled
        captured["server_configs"] = server_configs
        return None, []

    agent = _agent_with_mcp(
        McpServerConfig(
            name="agent-mcp",
            transport="websocket",
            url="ws://example.test/mcp",
        )
    )

    monkeypatch.setattr("core.runtime.agent.mcp_gateway.init_client_tools", fake_init_client_tools)

    await LeonAgent._init_mcp_tools(agent)

    assert captured["enabled"] is True
    server_configs = captured["server_configs"]
    assert isinstance(server_configs, dict)
    assert sorted(server_configs) == ["agent-mcp"]


@pytest.mark.asyncio
async def test_resolved_agent_config_without_mcp_disables_mcp(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_init_client_tools(*, enabled: bool, server_configs: dict[str, object]):
        captured["enabled"] = enabled
        captured["server_configs"] = server_configs
        return None, []

    agent = _agent_with_mcp()

    monkeypatch.setattr("core.runtime.agent.mcp_gateway.init_client_tools", fake_init_client_tools)

    await LeonAgent._init_mcp_tools(agent)

    assert captured["enabled"] is False
    assert captured["server_configs"] == {}


@pytest.mark.asyncio
async def test_missing_resolved_agent_config_disables_mcp(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_init_client_tools(*, enabled: bool, server_configs: dict[str, object]):
        captured["enabled"] = enabled
        captured["server_configs"] = server_configs
        return None, []

    agent = LeonAgent.__new__(LeonAgent)
    agent.config = LeonSettings()

    monkeypatch.setattr("core.runtime.agent.mcp_gateway.init_client_tools", fake_init_client_tools)

    await LeonAgent._init_mcp_tools(agent)

    assert captured["enabled"] is False
    assert captured["server_configs"] == {}
