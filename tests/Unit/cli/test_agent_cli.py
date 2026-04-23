from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace

import pytest


def test_agent_cli_whoami_uses_runtime_identity_and_display_lookup(monkeypatch: pytest.MonkeyPatch):
    from cli.agent import commands

    messaging = SimpleNamespace(resolve_display_user=lambda user_id: SimpleNamespace(id=user_id, display_name="Codex", type="agent"))
    runtime_read = SimpleNamespace(is_agent_actor_user=lambda user_id: True)
    out = StringIO()

    exit_code = commands.run_cli(
        ["whoami", "--agent-user-id", "agent-user-1"],
        messaging_client=messaging,
        runtime_read_client=runtime_read,
        stdout=out,
    )

    assert exit_code == 0
    assert json.loads(out.getvalue()) == {
        "agent_user_id": "agent-user-1",
        "display_name": "Codex",
        "type": "agent",
        "is_agent_actor": True,
    }


def test_agent_cli_send_defaults_to_enforce_caught_up(monkeypatch: pytest.MonkeyPatch):
    from cli.agent import commands

    captured: dict[str, object] = {}

    def _send(chat_id: str, sender_id: str, content: str, **kwargs):
        captured.update({
            "chat_id": chat_id,
            "sender_id": sender_id,
            "content": content,
            **kwargs,
        })
        return {"id": "msg-1", "chat_id": chat_id, "sender_id": sender_id, "content": content}

    messaging = SimpleNamespace(send=_send)
    out = StringIO()

    exit_code = commands.run_cli(
        ["send", "chat-1", "hello", "--agent-user-id", "agent-user-1"],
        messaging_client=messaging,
        runtime_read_client=SimpleNamespace(),
        stdout=out,
    )

    assert exit_code == 0
    assert captured["chat_id"] == "chat-1"
    assert captured["sender_id"] == "agent-user-1"
    assert captured["content"] == "hello"
    assert captured["enforce_caught_up"] is True


def test_agent_cli_config_reads_base_urls_and_identity_from_env(monkeypatch: pytest.MonkeyPatch):
    from cli.agent.config import load_cli_config

    monkeypatch.setenv("MYCEL_CHAT_BACKEND_URL", "http://chat-backend")
    monkeypatch.setenv("MYCEL_THREADS_BACKEND_URL", "http://threads-backend")
    monkeypatch.setenv("MYCEL_AGENT_USER_ID", "agent-user-1")

    cfg = load_cli_config(agent_user_id=None, chat_base_url=None, threads_base_url=None)

    assert cfg.agent_user_id == "agent-user-1"
    assert cfg.chat_base_url == "http://chat-backend"
    assert cfg.threads_base_url == "http://threads-backend"


def test_agent_cli_config_resolves_agent_user_from_profile_alias(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from cli.agent.config import load_cli_config

    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "codex-dev": {
                        "agent_user_id": "agent-user-42",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYCEL_AGENT_PROFILE_PATH", str(profile_path))

    cfg = load_cli_config(
        agent_user_id=None,
        agent_alias="codex-dev",
        chat_base_url="http://chat-backend",
        threads_base_url="http://threads-backend",
    )

    assert cfg.agent_user_id == "agent-user-42"


def test_agent_cli_send_accepts_profile_alias_for_identity(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from cli.agent import commands

    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "codex-dev": {
                        "agent_user_id": "agent-user-7",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYCEL_AGENT_PROFILE_PATH", str(profile_path))

    captured: dict[str, object] = {}

    def _send(chat_id: str, sender_id: str, content: str, **kwargs):
        captured.update({"chat_id": chat_id, "sender_id": sender_id, "content": content, **kwargs})
        return {"id": "msg-7", "chat_id": chat_id, "sender_id": sender_id, "content": content}

    exit_code = commands.run_cli(
        ["send", "chat-7", "hello", "--profile", "codex-dev"],
        messaging_client=SimpleNamespace(send=_send),
        runtime_read_client=SimpleNamespace(),
        stdout=StringIO(),
    )

    assert exit_code == 0
    assert captured["sender_id"] == "agent-user-7"


def test_agent_cli_external_create_calls_identity_client() -> None:
    from cli.agent import commands

    captured: dict[str, object] = {}

    def _create_external_user(*, user_id: str, display_name: str):
        captured["user_id"] = user_id
        captured["display_name"] = display_name
        return {"id": user_id, "type": "external", "display_name": display_name}

    exit_code = commands.run_cli(
        ["external", "create", "external-user-9", "Codex External", "--agent-user-id", "agent-user-1"],
        messaging_client=SimpleNamespace(),
        identity_client=SimpleNamespace(create_external_user=_create_external_user, list_users=lambda **_: []),
        runtime_read_client=SimpleNamespace(),
        stdout=StringIO(),
    )

    assert exit_code == 0
    assert captured == {"user_id": "external-user-9", "display_name": "Codex External"}

def test_agent_cli_external_list_calls_identity_client() -> None:
    from cli.agent import commands

    out = StringIO()
    exit_code = commands.run_cli(
        ['external', 'list', '--agent-user-id', 'agent-user-1'],
        messaging_client=SimpleNamespace(),
        identity_client=SimpleNamespace(
            create_external_user=lambda **_: (_ for _ in ()).throw(AssertionError('create not expected')),
            list_users=lambda **kwargs: [{'id': 'external-user-1', 'type': kwargs['user_type'], 'display_name': 'Codex External'}],
        ),
        runtime_read_client=SimpleNamespace(),
        stdout=out,
    )

    assert exit_code == 0
    assert json.loads(out.getvalue()) == [
        {'id': 'external-user-1', 'type': 'external', 'display_name': 'Codex External'}
    ]

def test_agent_cli_chats_list_calls_messaging_client() -> None:
    from cli.agent import commands

    out = StringIO()
    exit_code = commands.run_cli(
        ['chats', 'list', '--agent-user-id', 'agent-user-1'],
        messaging_client=SimpleNamespace(list_chats_for_user=lambda user_id: [{'id': 'chat-1', 'user_id': user_id}]),
        identity_client=SimpleNamespace(create_external_user=lambda **_: None, list_users=lambda **_: []),
        runtime_read_client=SimpleNamespace(),
        stdout=out,
    )

    assert exit_code == 0
    assert json.loads(out.getvalue()) == [{'id': 'chat-1', 'user_id': 'agent-user-1'}]


def test_agent_cli_messages_list_uses_viewer_identity() -> None:
    from cli.agent import commands

    captured: dict[str, object] = {}

    def _list_messages(chat_id: str, *, limit: int, before: str | None, viewer_id: str):
        captured.update({'chat_id': chat_id, 'limit': limit, 'before': before, 'viewer_id': viewer_id})
        return [{'id': 'msg-1'}]

    out = StringIO()
    exit_code = commands.run_cli(
        ['messages', 'list', 'chat-1', '--limit', '10', '--agent-user-id', 'agent-user-1'],
        messaging_client=SimpleNamespace(list_messages=_list_messages),
        identity_client=SimpleNamespace(create_external_user=lambda **_: None, list_users=lambda **_: []),
        runtime_read_client=SimpleNamespace(),
        stdout=out,
    )

    assert exit_code == 0
    assert captured == {'chat_id': 'chat-1', 'limit': 10, 'before': None, 'viewer_id': 'agent-user-1'}
    assert json.loads(out.getvalue()) == [{'id': 'msg-1'}]


def test_agent_cli_messages_unread_calls_unread_list() -> None:
    from cli.agent import commands

    out = StringIO()
    exit_code = commands.run_cli(
        ['messages', 'unread', 'chat-1', '--agent-user-id', 'agent-user-1'],
        messaging_client=SimpleNamespace(list_unread=lambda chat_id, user_id: [{'chat_id': chat_id, 'user_id': user_id}]),
        identity_client=SimpleNamespace(create_external_user=lambda **_: None, list_users=lambda **_: []),
        runtime_read_client=SimpleNamespace(),
        stdout=out,
    )

    assert exit_code == 0
    assert json.loads(out.getvalue()) == [{'chat_id': 'chat-1', 'user_id': 'agent-user-1'}]


def test_agent_cli_read_marks_read_for_agent_identity() -> None:
    from cli.agent import commands

    captured: dict[str, object] = {}

    def _mark_read(chat_id: str, user_id: str):
        captured.update({'chat_id': chat_id, 'user_id': user_id})

    out = StringIO()
    exit_code = commands.run_cli(
        ['read', 'chat-1', '--agent-user-id', 'agent-user-1'],
        messaging_client=SimpleNamespace(mark_read=_mark_read),
        identity_client=SimpleNamespace(create_external_user=lambda **_: None, list_users=lambda **_: []),
        runtime_read_client=SimpleNamespace(),
        stdout=out,
    )

    assert exit_code == 0
    assert captured == {'chat_id': 'chat-1', 'user_id': 'agent-user-1'}
    assert json.loads(out.getvalue()) == {'status': 'ok', 'chat_id': 'chat-1', 'agent_user_id': 'agent-user-1'}


def test_agent_cli_direct_uses_agent_identity() -> None:
    from cli.agent import commands

    out = StringIO()
    exit_code = commands.run_cli(
        ['direct', 'target-user-1', '--agent-user-id', 'agent-user-1'],
        messaging_client=SimpleNamespace(find_direct_chat_id=lambda actor_id, target_id: f'{actor_id}:{target_id}:chat'),
        identity_client=SimpleNamespace(create_external_user=lambda **_: None, list_users=lambda **_: []),
        runtime_read_client=SimpleNamespace(),
        stdout=out,
    )

    assert exit_code == 0
    assert json.loads(out.getvalue()) == {
        'chat_id': 'agent-user-1:target-user-1:chat',
        'agent_user_id': 'agent-user-1',
        'target_id': 'target-user-1',
    }
