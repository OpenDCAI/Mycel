import json

from backend.web.services import resource_service
from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


def test_list_resource_providers_uses_abstract_terminals_when_chat_sessions_missing(tmp_path, monkeypatch):
    sandbox_db = tmp_path / "sandbox.db"
    sandboxes_dir = tmp_path / "sandboxes"
    sandboxes_dir.mkdir(parents=True)
    (sandboxes_dir / "local.json").write_text(json.dumps({"provider": "local"}))

    lease_repo = SQLiteLeaseRepo(db_path=sandbox_db)
    terminal_repo = SQLiteTerminalRepo(db_path=sandbox_db)
    chat_session_repo = SQLiteChatSessionRepo(db_path=sandbox_db)
    try:
        lease_repo.create(
            lease_id="lease-1",
            provider_name="local",
            recipe_id="local:default",
        )
        terminal_repo.create(
            terminal_id="term-1",
            thread_id="thread-1",
            lease_id="lease-1",
            initial_cwd="/tmp/one",
        )
        terminal_repo.create(
            terminal_id="term-2",
            thread_id="thread-2",
            lease_id="lease-1",
            initial_cwd="/tmp/two",
        )
    finally:
        lease_repo.close()
        terminal_repo.close()
        chat_session_repo.close()

    monkeypatch.setattr(resource_service, "SANDBOXES_DIR", sandboxes_dir)
    monkeypatch.setattr(resource_service, "available_sandbox_types", lambda: [{"name": "local", "available": True}])
    monkeypatch.setattr(
        resource_service,
        "SQLiteSandboxMonitorRepo",
        lambda: SQLiteSandboxMonitorRepo(db_path=sandbox_db),
    )
    monkeypatch.setattr(
        resource_service,
        "_thread_agent_refs",
        lambda _thread_ids: {"thread-1": "member-1", "thread-2": "member-2"},
    )
    monkeypatch.setattr(
        resource_service,
        "_member_name_map",
        lambda: {"member-1": "Toad", "member-2": "Morel"},
    )

    payload = resource_service.list_resource_providers()
    sessions = payload["providers"][0]["sessions"]

    assert [(item["threadId"], item["memberName"]) for item in sessions] == [
        ("thread-1", "Toad"),
        ("thread-2", "Morel"),
    ]
