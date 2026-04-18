from types import SimpleNamespace

import pytest

from backend.web.services import monitor_service, sandbox_service


class _FailingManager:
    def __init__(self) -> None:
        self.provider = SimpleNamespace(name="daytona", list_provider_sessions=lambda: [])
        self.lease_store = SimpleNamespace(list_by_provider=lambda _provider_name: [])
        self.provider_capability = SimpleNamespace(inspect_visible=True)

    def list_sessions(self):
        raise AssertionError("provider orphan runtime endpoint must not refresh all lease sessions")


def _provider_runtime(runtime_id: str, status: str = "paused"):
    return SimpleNamespace(session_id=runtime_id, status=status)


def test_monitor_provider_orphan_runtimes_do_not_refresh_all_lease_sessions(monkeypatch):
    manager = _FailingManager()

    monkeypatch.setattr(sandbox_service, "init_providers_and_managers", lambda: ({}, {"daytona": manager}))

    assert monitor_service.list_monitor_provider_orphan_runtimes() == {"count": 0, "runtimes": []}


def test_load_provider_orphan_sessions_excludes_covered_provider_runtimes():
    manager = SimpleNamespace(
        provider=SimpleNamespace(
            name="daytona",
            list_provider_sessions=lambda: [
                _provider_runtime("covered-runtime"),
                _provider_runtime("orphan-paused", "paused"),
                _provider_runtime("orphan-running", "running"),
                _provider_runtime("deleted-one", "deleted"),
            ],
        ),
        lease_store=SimpleNamespace(list_by_provider=lambda _provider_name: [{"current_instance_id": "covered-runtime"}]),
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


def test_load_provider_orphan_sessions_rejects_non_list_provider_result():
    manager = SimpleNamespace(
        provider=SimpleNamespace(name="daytona", list_provider_sessions=lambda: (_provider_runtime("orphan"),)),
        lease_store=SimpleNamespace(list_by_provider=lambda _provider_name: []),
        provider_capability=SimpleNamespace(inspect_visible=False),
    )

    with pytest.raises(TypeError, match="daytona.list_provider_sessions must return list"):
        sandbox_service.load_provider_orphan_sessions({"daytona": manager})
