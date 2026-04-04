import json
from types import SimpleNamespace

from sandbox.providers.agentbay import AgentBayProvider


def _provider_with_fake_client(fake_client) -> AgentBayProvider:
    provider = AgentBayProvider.__new__(AgentBayProvider)
    provider.name = "agentbay"
    provider.client = fake_client
    provider.default_context_path = "/home/wuying"
    provider.image_id = None
    provider._sessions = {}
    provider._capability = AgentBayProvider.CAPABILITY
    return provider


def test_create_session_refreshes_agentbay_session_when_direct_call_fields_missing():
    raw_session = SimpleNamespace(session_id="sess-123", token="", link_url="", mcpTools=[])
    hydrated_session = SimpleNamespace(session_id="sess-123", token="tok", link_url="https://link", mcpTools=[object()])
    fake_client = SimpleNamespace(
        context=SimpleNamespace(get=lambda *args, **kwargs: None),
        create=lambda params: SimpleNamespace(success=True, session=raw_session, error_message=""),
        get=lambda session_id: SimpleNamespace(success=True, session=hydrated_session, error_message=""),
    )
    provider = _provider_with_fake_client(fake_client)

    info = provider.create_session()

    assert info.session_id == "sess-123"
    assert provider._sessions["sess-123"] is hydrated_session


def test_get_session_refreshes_stale_cached_agentbay_session():
    stale_session = SimpleNamespace(session_id="sess-123", token="", link_url="", mcpTools=[])
    hydrated_session = SimpleNamespace(session_id="sess-123", token="tok", link_url="https://link", mcpTools=[object()])
    fake_client = SimpleNamespace(
        get=lambda session_id: SimpleNamespace(success=True, session=hydrated_session, error_message=""),
    )
    provider = _provider_with_fake_client(fake_client)
    provider._sessions["sess-123"] = stale_session

    session = provider._get_session("sess-123")

    assert session is hydrated_session
    assert provider._sessions["sess-123"] is hydrated_session


def test_execute_prefers_link_url_shell_path_when_session_has_direct_call_metadata():
    calls: list[tuple[str, object]] = []

    class _Tool:
        name = "shell"
        server = "wuying_shell"

    def _link(tool_name: str, args: dict, server_name: str):
        calls.append(("link", {"tool": tool_name, "args": args, "server": server_name}))
        return SimpleNamespace(
            success=True,
            data=json.dumps({"stdout": "/home/wuying\n", "stderr": "", "exit_code": 0}),
            error_message="",
        )

    def _command_execute(**kwargs):
        calls.append(("command", kwargs))
        return SimpleNamespace(success=False, output="", error_message="should not be used")

    session = SimpleNamespace(
        session_id="sess-123",
        token="tok",
        link_url="https://link",
        mcpTools=[_Tool()],
        _get_mcp_server_for_tool=lambda tool_name: "wuying_shell" if tool_name == "shell" else None,
        _call_mcp_tool_link_url=_link,
        command=SimpleNamespace(execute_command=_command_execute),
    )
    provider = _provider_with_fake_client(SimpleNamespace())
    provider._sessions["sess-123"] = session

    result = provider.execute("sess-123", "pwd", timeout_ms=5000, cwd="/home/wuying")

    assert result.output == "/home/wuying\n"
    assert result.exit_code == 0
    assert result.error is None
    assert calls == [
        (
            "link",
            {
                "tool": "shell",
                "args": {"command": "pwd", "timeout_ms": 5000, "cwd": "/home/wuying"},
                "server": "wuying_shell",
            },
        )
    ]
