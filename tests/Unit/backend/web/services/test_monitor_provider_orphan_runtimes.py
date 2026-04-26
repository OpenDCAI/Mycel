from types import SimpleNamespace

import pytest

from backend.monitor.application.use_cases import provider_runtimes as monitor_provider_runtime_service
from backend.monitor.infrastructure.providers import provider_runtime_inventory_service as monitor_provider_runtime_inventory_service
from backend.sandboxes import service as sandbox_service

SANDBOX_RUNTIME_KEY = "sandbox_runtime_" + "id"


class _FailingManager:
    def __init__(self) -> None:
        self.provider = SimpleNamespace(name="daytona", list_provider_runtimes=lambda: [])
        self.sandbox_runtime_store = SimpleNamespace(list_by_provider=lambda _provider_name: [])
        self.provider_capability = SimpleNamespace(inspect_visible=True)

    def list_sessions(self):
        raise AssertionError("provider orphan runtime endpoint must not refresh all managed runtime rows")


def _provider_runtime(runtime_id: str, status: str = "paused"):
    return SimpleNamespace(session_id=runtime_id, status=status)


def test_monitor_provider_orphan_runtimes_do_not_refresh_all_managed_runtime_rows(monkeypatch):
    monkeypatch.setattr(monitor_provider_runtime_inventory_service, "load_provider_orphan_runtime_rows", lambda: [])

    assert monitor_provider_runtime_service.list_monitor_provider_orphan_runtimes() == {"count": 0, "runtimes": []}


def test_load_provider_orphan_runtimes_excludes_covered_provider_runtimes():
    manager = SimpleNamespace(
        provider=SimpleNamespace(
            name="daytona",
            list_provider_runtimes=lambda: [
                _provider_runtime("covered-runtime"),
                _provider_runtime("orphan-paused", "paused"),
                _provider_runtime("orphan-running", "running"),
                _provider_runtime("deleted-one", "deleted"),
            ],
        ),
        sandbox_runtime_store=SimpleNamespace(list_by_provider=lambda _provider_name: [{"current_instance_id": "covered-runtime"}]),
        provider_capability=SimpleNamespace(inspect_visible=False),
    )

    assert sandbox_service.load_provider_orphan_runtimes({"daytona": manager}) == [
        {
            "session_id": "orphan-paused",
            "thread_id": "(orphan)",
            "provider": "daytona",
            "status": "paused",
            "created_at": None,
            "last_active": None,
            SANDBOX_RUNTIME_KEY: None,
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
            SANDBOX_RUNTIME_KEY: None,
            "instance_id": "orphan-running",
            "chat_session_id": None,
            "source": "provider_orphan",
            "inspect_visible": False,
        },
    ]


def test_load_provider_orphan_runtimes_rejects_non_list_provider_result():
    manager = SimpleNamespace(
        provider=SimpleNamespace(name="daytona", list_provider_runtimes=lambda: (_provider_runtime("orphan"),)),
        sandbox_runtime_store=SimpleNamespace(list_by_provider=lambda _provider_name: []),
        provider_capability=SimpleNamespace(inspect_visible=False),
    )

    with pytest.raises(TypeError, match="daytona.list_provider_runtimes must return list"):
        sandbox_service.load_provider_orphan_runtimes({"daytona": manager})
