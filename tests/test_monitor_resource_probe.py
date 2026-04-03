from unittest.mock import MagicMock

from backend.web.services import resource_service


class _FakeProvider:
    def get_metrics(self, session_id: str):
        return None


def _make_probe_repo(targets: list[dict]):
    repo = MagicMock()
    repo.list_probe_targets.return_value = targets
    repo.close.return_value = None
    return repo


def test_refresh_resource_snapshots_probes_running_leases_only(monkeypatch):
    monkeypatch.setattr(resource_service, "ensure_resource_snapshot_table", lambda: None)
    monkeypatch.setattr(
        resource_service,
        "make_sandbox_monitor_repo",
        lambda: _make_probe_repo(
            [
                {"provider_name": "p1", "instance_id": "s-1", "lease_id": "l-1", "observed_state": "detached"},
                {"provider_name": "p1", "instance_id": "s-2", "lease_id": "l-2", "observed_state": "paused"},
            ]
        ),
    )
    monkeypatch.setattr(resource_service, "build_provider_from_config_name", lambda _: _FakeProvider())

    calls: list[dict] = []

    def _fake_probe(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "error": None}

    monkeypatch.setattr(resource_service, "probe_and_upsert_for_instance", _fake_probe)

    result = resource_service.refresh_resource_snapshots()
    assert result["probed"] == 2
    assert result["errors"] == 0
    assert result["running_targets"] == 1
    assert result["non_running_targets"] == 1
    assert {call["lease_id"] for call in calls} == {"l-1", "l-2"}
    modes = {call["lease_id"]: call["probe_mode"] for call in calls}
    assert modes["l-1"] == "running_runtime"
    assert modes["l-2"] == "non_running_sdk"


def test_refresh_resource_snapshots_counts_provider_build_error(monkeypatch):
    monkeypatch.setattr(resource_service, "ensure_resource_snapshot_table", lambda: None)
    monkeypatch.setattr(
        resource_service,
        "make_sandbox_monitor_repo",
        lambda: _make_probe_repo(
            [
                {"provider_name": "p-missing", "instance_id": "s-1", "lease_id": "l-1", "observed_state": "detached"},
            ]
        ),
    )
    monkeypatch.setattr(resource_service, "build_provider_from_config_name", lambda _: None)
    upserts: list[dict] = []
    monkeypatch.setattr(
        resource_service,
        "upsert_resource_snapshot",
        lambda **kwargs: upserts.append(kwargs),
    )

    result = resource_service.refresh_resource_snapshots()
    assert result["probed"] == 0
    assert result["errors"] == 1
    assert result["running_targets"] == 1
    assert result["non_running_targets"] == 0
    assert len(upserts) == 1
    assert upserts[0]["lease_id"] == "l-1"
    assert upserts[0]["probe_mode"] == "running_runtime"
    assert upserts[0]["probe_error"] == "provider init failed: p-missing"
