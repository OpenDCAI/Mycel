import json
from dataclasses import replace
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


def test_destroy_session_skips_sync_when_pause_capability_is_disabled():
    calls: list[bool] = []

    class _DeleteResult:
        success = True

    class _Session:
        session_id = "sess-123"
        token = "tok"
        link_url = "https://link"
        mcpTools = [object()]

        def delete(self, *, sync_context: bool):
            calls.append(sync_context)
            return _DeleteResult()

    provider = _provider_with_fake_client(SimpleNamespace())
    provider._capability = replace(AgentBayProvider.CAPABILITY, can_pause=False, can_resume=False)
    provider._sessions["sess-123"] = _Session()

    assert provider.destroy_session("sess-123") is True
    assert calls == [False]
    assert "sess-123" not in provider._sessions


def test_execute_prefers_link_url_shell_path_when_session_has_direct_call_metadata():
    calls: list[tuple[str, object]] = []

    class _Tool:
        name = "shell"
        server = "wuying_shell"

    def _command_execute(**kwargs):
        calls.append(("command", kwargs))
        return SimpleNamespace(success=False, output="", error_message="should not be used")

    session = SimpleNamespace(
        session_id="sess-123",
        token="tok",
        link_url="https://link",
        mcpTools=[_Tool()],
        _get_mcp_server_for_tool=lambda tool_name: "wuying_shell" if tool_name == "shell" else None,
        command=SimpleNamespace(execute_command=_command_execute),
    )
    provider = _provider_with_fake_client(SimpleNamespace())
    provider._sessions["sess-123"] = session
    provider._call_link_url_tool = lambda session, tool_name, args, server_name: (
        calls.append(("link", {"tool": tool_name, "args": args, "server": server_name}))
        or AgentBayProvider._provider_exec_result_from_tool_result(
            SimpleNamespace(
                success=True,
                data=json.dumps({"stdout": "/home/wuying\n", "stderr": "", "exit_code": 0}),
                error_message="",
            )
        )
    )

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


def test_get_session_hydrates_sdk_shape_session_from_raw_get_session_metadata():
    sdk_shape_session = SimpleNamespace(
        session_id="sess-123",
        token="tok",
        resource_url="https://resource",
        mcp_tools=[],
    )
    fake_response = SimpleNamespace(
        to_map=lambda: {
            "body": {
                "Success": True,
                "Data": {
                    "LinkUrl": "https://link",
                    "Token": "tok",
                    "ToolList": [{"Name": "shell", "Server": "wuying_shell"}],
                },
            }
        }
    )
    fake_client = SimpleNamespace(
        api_key="api-key",
        get=lambda session_id: SimpleNamespace(success=True, session=sdk_shape_session, error_message=""),
        client=SimpleNamespace(get_session=lambda request: fake_response),
    )
    provider = _provider_with_fake_client(fake_client)

    session = provider._get_session("sess-123")

    assert session is sdk_shape_session
    assert getattr(session, "link_url") == "https://link"
    assert getattr(session, "token") == "tok"
    assert len(getattr(session, "mcp_tools")) == 1
    assert getattr(session, "mcpTools") == getattr(session, "mcp_tools")
    assert provider._resolve_shell_server(session) == "wuying_shell"


def test_execute_prefers_link_url_shell_path_for_sdk_shape_session():
    calls: list[tuple[str, object]] = []

    def _command_execute(**kwargs):
        calls.append(("command", kwargs))
        return SimpleNamespace(success=False, output="", error_message="should not be used")

    session = SimpleNamespace(
        session_id="sess-123",
        token="tok",
        link_url="https://link",
        mcp_tools=[SimpleNamespace(name="shell", server="wuying_shell")],
        _find_server_for_tool=lambda tool_name: "wuying_shell" if tool_name == "shell" else "",
        command=SimpleNamespace(execute_command=_command_execute),
    )
    provider = _provider_with_fake_client(SimpleNamespace())
    provider._sessions["sess-123"] = session
    provider._call_link_url_tool = lambda session, tool_name, args, server_name: (
        calls.append(("link", {"tool": tool_name, "args": args, "server": server_name}))
        or AgentBayProvider._provider_exec_result_from_tool_result(
            SimpleNamespace(
                success=True,
                data=json.dumps({"stdout": "/home/wuying\n", "stderr": "", "exit_code": 0}),
                error_message="",
            )
        )
    )

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


def test_resolve_shell_server_falls_back_to_mcp_tools_when_sdk_resolver_raises():
    session = SimpleNamespace(
        mcp_tools=[SimpleNamespace(name="shell", server="wuying_shell")],
        _find_server_for_tool=lambda tool_name: (_ for _ in ()).throw(StopIteration()),
    )

    assert AgentBayProvider._resolve_shell_server(session) == "wuying_shell"


def test_execute_uses_provider_owned_link_call_instead_of_sdk_private_method():
    calls: list[tuple[str, object]] = []

    def _sdk_link(*args, **kwargs):
        raise StopIteration()

    def _provider_link(session: object, tool_name: str, args: dict, server_name: str):
        calls.append(("provider-link", {"tool": tool_name, "args": args, "server": server_name}))
        return AgentBayProvider._provider_exec_result_from_tool_result(
            SimpleNamespace(
                success=True,
                data=json.dumps({"stdout": "/home/wuying\n", "stderr": "", "exit_code": 0}),
                error_message="",
            )
        )

    session = SimpleNamespace(
        session_id="sess-123",
        token="tok",
        link_url="https://link",
        mcp_tools=[SimpleNamespace(name="shell", server="wuying_shell")],
        _find_server_for_tool=lambda tool_name: "wuying_shell",
        _call_mcp_tool_link_url=_sdk_link,
        command=SimpleNamespace(execute_command=lambda **kwargs: None),
    )
    provider = _provider_with_fake_client(SimpleNamespace())
    provider._sessions["sess-123"] = session
    provider._call_link_url_tool = _provider_link

    result = provider.execute("sess-123", "pwd", timeout_ms=5000, cwd="/home/wuying")

    assert result.output == "/home/wuying\n"
    assert result.exit_code == 0
    assert result.error is None
    assert calls == [
        (
            "provider-link",
            {
                "tool": "shell",
                "args": {"command": "pwd", "timeout_ms": 5000, "cwd": "/home/wuying"},
                "server": "wuying_shell",
            },
        )
    ]
