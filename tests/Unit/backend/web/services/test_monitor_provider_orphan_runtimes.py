import inspect
from types import SimpleNamespace

import pytest

from backend import sandbox_runtime_mutations as neutral_sandbox_runtime_mutations
from backend.monitor.application.use_cases import provider_runtimes as monitor_provider_runtime_service
from backend.web.services import sandbox_service

LOWER_RUNTIME_KEY = "lease_" + "id"


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
    source = inspect.getsource(monitor_provider_runtime_service.request_monitor_provider_orphan_runtime_cleanup)
    removed_name = "session" + "_truth"
    removed_field = "session" + "_id"

    assert removed_name not in source
    assert removed_field not in source
    assert "runtime_truth" in source


def test_monitor_provider_orphan_runtimes_do_not_refresh_all_managed_runtime_rows(monkeypatch):
    monkeypatch.setattr(sandbox_service, "list_provider_orphan_runtimes", lambda: [])

    assert monitor_provider_runtime_service.list_monitor_provider_orphan_runtimes() == {"count": 0, "runtimes": []}


def test_monitor_provider_orphan_inventory_uses_sandbox_service_data_boundary():
    from backend.monitor.infrastructure.providers import provider_runtime_inventory_service

    source = inspect.getsource(provider_runtime_inventory_service)

    assert "init_providers_and_managers" not in source
    assert "load_provider_orphan_runtimes(" not in source
    assert "list_provider_orphan_runtimes(" in source


def test_sandbox_service_keeps_provider_orphan_inventory_compat_surface():
    source = inspect.getsource(sandbox_service)

    assert "sandbox_inventory.load_provider_orphan_runtimes(" in source
    assert "sandbox_inventory.list_provider_orphan_runtimes(" in source


def test_sandbox_runtime_mutations_owner_moves_out_of_sandbox_service():
    source = inspect.getsource(neutral_sandbox_runtime_mutations)

    assert "backend.web.services import sandbox_service" not in source
    assert "backend.sandbox_inventory" in source


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
            LOWER_RUNTIME_KEY: None,
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
            LOWER_RUNTIME_KEY: None,
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
