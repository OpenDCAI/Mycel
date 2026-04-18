import inspect
from types import SimpleNamespace

import pytest

from backend.web.services import monitor_service, sandbox_service


class _FailingManager:
    def __init__(self) -> None:
        self.provider = SimpleNamespace(name="daytona", list_provider_runtimes=lambda: [])
        self.lease_store = SimpleNamespace(list_by_provider=lambda _provider_name: [])
        self.provider_capability = SimpleNamespace(inspect_visible=True)

    def list_sessions(self):
        raise AssertionError("provider orphan runtime endpoint must not refresh all managed runtime rows")


def _provider_runtime(runtime_id: str, status: str = "paused"):
    return SimpleNamespace(session_id=runtime_id, status=status)


def test_provider_orphan_runtime_cleanup_uses_runtime_truth_name():
    source = inspect.getsource(monitor_service.request_monitor_provider_orphan_runtime_cleanup)
    removed_name = "session" + "_truth"

    assert removed_name not in source
    assert "runtime_truth" in source


def test_monitor_provider_orphan_runtimes_do_not_refresh_all_managed_runtime_rows(monkeypatch):
    manager = _FailingManager()

    monkeypatch.setattr(sandbox_service, "init_providers_and_managers", lambda: ({}, {"daytona": manager}))

    assert monitor_service.list_monitor_provider_orphan_runtimes() == {"count": 0, "runtimes": []}


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
        lease_store=SimpleNamespace(list_by_provider=lambda _provider_name: [{"current_instance_id": "covered-runtime"}]),
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


def test_load_provider_orphan_runtimes_rejects_non_list_provider_result():
    manager = SimpleNamespace(
        provider=SimpleNamespace(name="daytona", list_provider_runtimes=lambda: (_provider_runtime("orphan"),)),
        lease_store=SimpleNamespace(list_by_provider=lambda _provider_name: []),
        provider_capability=SimpleNamespace(inspect_visible=False),
    )

    with pytest.raises(TypeError, match="daytona.list_provider_runtimes must return list"):
        sandbox_service.load_provider_orphan_runtimes({"daytona": manager})
