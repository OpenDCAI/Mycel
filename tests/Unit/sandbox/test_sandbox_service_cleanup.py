from types import SimpleNamespace

from backend.sandboxes import service as sandbox_service

LOWER_RUNTIME_KEY = "lease_" + "id"


def test_destroy_sandbox_runtime_uses_manager_destroy_resources(monkeypatch):
    calls: list[str] = []

    class _Manager:
        terminal_store = SimpleNamespace(list_all=lambda: [], delete=lambda _terminal_id: None)

        def get_sandbox_runtime(self, lower_runtime_id: str):
            return SimpleNamespace(**{LOWER_RUNTIME_KEY: lower_runtime_id})

        def destroy_sandbox_runtime_resources(self, lower_runtime_id: str) -> bool:
            calls.append(lower_runtime_id)
            return True

    monkeypatch.setattr(
        sandbox_service,
        "init_providers_and_managers",
        lambda: ({}, {"daytona_selfhost": _Manager()}),
    )
    monkeypatch.setattr(
        sandbox_service,
        "build_storage_container",
        lambda: SimpleNamespace(thread_repo=lambda: SimpleNamespace(close=lambda: None)),
    )

    result = sandbox_service.destroy_sandbox_runtime(sandbox_runtime_handle="lease-1", provider_name="daytona_selfhost")

    assert result == {
        "ok": True,
        "action": "destroy",
        "sandbox_runtime_handle": "lease-1",
        "provider": "daytona_selfhost",
        "mode": "manager_runtime",
    }
    assert calls == ["lease-1"]


def test_destroy_sandbox_runtime_prunes_stale_terminals_before_destroy(monkeypatch):
    deleted_terminals: list[str] = []
    destroyed: list[str] = []
    deleted_thread_chats: list[tuple[str, str]] = []
    terminal_rows = [
        {"terminal_id": "term-stale", LOWER_RUNTIME_KEY: "lease-1", "thread_id": "thread-missing"},
    ]

    class _Manager:
        terminal_store = SimpleNamespace(
            list_all=lambda: list(terminal_rows),
            delete=lambda terminal_id: deleted_terminals.append(terminal_id),
        )
        session_manager = SimpleNamespace(
            delete_thread=lambda thread_id, reason="thread_deleted": deleted_thread_chats.append((thread_id, reason))
        )

        def get_sandbox_runtime(self, lower_runtime_id: str):
            return SimpleNamespace(**{LOWER_RUNTIME_KEY: lower_runtime_id})

        def destroy_sandbox_runtime_resources(self, lower_runtime_id: str) -> bool:
            destroyed.append(lower_runtime_id)
            return True

    class _ThreadRepo:
        def get_by_id(self, thread_id: str):
            return None

        def close(self) -> None:
            return None

    class _Container:
        def thread_repo(self):
            return _ThreadRepo()

    monkeypatch.setattr(
        sandbox_service,
        "init_providers_and_managers",
        lambda: ({}, {"daytona_selfhost": _Manager()}),
    )
    monkeypatch.setattr(sandbox_service, "build_storage_container", lambda: _Container())

    result = sandbox_service.destroy_sandbox_runtime(sandbox_runtime_handle="lease-1", provider_name="daytona_selfhost")

    assert result["ok"] is True
    assert deleted_thread_chats == [("thread-missing", "stale_terminal_pruned")]
    assert deleted_terminals == ["term-stale"]
    assert destroyed == ["lease-1"]


def test_destroy_sandbox_runtime_detaches_threads_with_sandbox_cleanup_reason(monkeypatch):
    deleted_terminals: list[str] = []
    destroyed: list[str] = []
    deleted_thread_chats: list[tuple[str, str]] = []
    terminal_rows = [
        {"terminal_id": "term-live", LOWER_RUNTIME_KEY: "lease-1", "thread_id": "thread-live"},
    ]

    class _Manager:
        terminal_store = SimpleNamespace(
            list_all=lambda: list(terminal_rows),
            delete=lambda terminal_id: deleted_terminals.append(terminal_id),
        )
        session_manager = SimpleNamespace(
            delete_thread=lambda thread_id, reason="thread_deleted": deleted_thread_chats.append((thread_id, reason))
        )

        def get_sandbox_runtime(self, lower_runtime_id: str):
            return SimpleNamespace(**{LOWER_RUNTIME_KEY: lower_runtime_id})

        def destroy_sandbox_runtime_resources(self, lower_runtime_id: str) -> bool:
            destroyed.append(lower_runtime_id)
            return True

    class _ThreadRepo:
        def get_by_id(self, thread_id: str):
            return {"id": thread_id}

        def close(self) -> None:
            return None

    class _Container:
        def thread_repo(self):
            return _ThreadRepo()

    monkeypatch.setattr(
        sandbox_service,
        "init_providers_and_managers",
        lambda: ({}, {"daytona_selfhost": _Manager()}),
    )
    monkeypatch.setattr(sandbox_service, "build_storage_container", lambda: _Container())

    result = sandbox_service.destroy_sandbox_runtime(
        sandbox_runtime_handle="lease-1",
        provider_name="daytona_selfhost",
        detach_thread_bindings=True,
    )

    assert result["ok"] is True
    assert deleted_thread_chats == [("thread-live", "detached_sandbox_cleanup")]
    assert deleted_terminals == ["term-live"]
    assert destroyed == ["lease-1"]
