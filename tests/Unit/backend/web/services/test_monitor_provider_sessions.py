from types import SimpleNamespace

from backend.web.services import monitor_service, sandbox_service


class _FailingManager:
    def __init__(self) -> None:
        self.provider = SimpleNamespace(name="daytona", list_provider_sessions=lambda: [])
        self.lease_store = SimpleNamespace(list_by_provider=lambda _provider_name: [])
        self.provider_capability = SimpleNamespace(inspect_visible=True)

    def list_sessions(self):
        raise AssertionError("provider orphan endpoint must not refresh all lease sessions")


def _provider_session(session_id: str, status: str = "paused"):
    return SimpleNamespace(session_id=session_id, status=status)


def test_monitor_provider_orphan_runtimes_do_not_refresh_all_lease_sessions(monkeypatch):
    manager = _FailingManager()

    monkeypatch.setattr(sandbox_service, "init_providers_and_managers", lambda: ({}, {"daytona": manager}))

    assert monitor_service.list_monitor_provider_orphan_runtimes() == {"count": 0, "runtimes": []}


def test_load_provider_orphan_sessions_excludes_lease_backed_provider_sessions():
    manager = SimpleNamespace(
        provider=SimpleNamespace(
            name="daytona",
            list_provider_sessions=lambda: [
                _provider_session("lease-backed"),
                _provider_session("orphan-paused", "paused"),
                _provider_session("orphan-running", "running"),
                _provider_session("deleted-one", "deleted"),
            ],
        ),
        lease_store=SimpleNamespace(list_by_provider=lambda _provider_name: [{"current_instance_id": "lease-backed"}]),
        provider_capability=SimpleNamespace(inspect_visible=False),
    )

    assert sandbox_service.load_provider_orphan_sessions({"daytona": manager}) == [
        {
            "session_id": "orphan-paused",
            "thread_id": "(orphan)",
            "provider": "daytona",
            "status": "paused",
            "created_at": None,
            "last_active": None,
            "lease_id": None,
            "instance_id": "orphan-paused",
            "chat_session_id": None,
            "source": "provider_orphan",
            "inspect_visible": False,
        },
        {
            "session_id": "orphan-running",
            "thread_id": "(orphan)",
            "provider": "daytona",
            "status": "running",
            "created_at": None,
            "last_active": None,
            "lease_id": None,
            "instance_id": "orphan-running",
            "chat_session_id": None,
            "source": "provider_orphan",
            "inspect_visible": False,
        },
    ]
