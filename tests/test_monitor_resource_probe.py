from backend.web.monitor_core import resource_probe


class _FakeProvider:
    def get_metrics(self, session_id: str):
        return None


def test_refresh_resource_snapshots_probes_running_leases_only(monkeypatch):
    monkeypatch.setattr(resource_probe, "ensure_resource_snapshot_table", lambda: None)
    monkeypatch.setattr(
        resource_probe,
        "_running_lease_instances",
        lambda: [
            {"provider_name": "p1", "instance_id": "s-1", "lease_id": "l-1", "observed_state": "running"},
            {"provider_name": "p1", "instance_id": "s-2", "lease_id": "l-2", "observed_state": "running"},
        ],
    )
    monkeypatch.setattr(resource_probe, "build_provider_from_config_name", lambda _: _FakeProvider())

    calls: list[dict] = []

    def _fake_probe(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "error": None}

    monkeypatch.setattr(resource_probe, "probe_and_upsert_for_instance", _fake_probe)

    result = resource_probe.refresh_resource_snapshots()
    assert result["probed"] == 2
    assert result["errors"] == 0
    assert {call["lease_id"] for call in calls} == {"l-1", "l-2"}
    assert calls[0]["probe_mode"] == "running_runtime"


def test_refresh_resource_snapshots_counts_provider_build_error(monkeypatch):
    monkeypatch.setattr(resource_probe, "ensure_resource_snapshot_table", lambda: None)
    monkeypatch.setattr(
        resource_probe,
        "_running_lease_instances",
        lambda: [
            {"provider_name": "p-missing", "instance_id": "s-1", "lease_id": "l-1", "observed_state": "running"},
        ],
    )
    monkeypatch.setattr(resource_probe, "build_provider_from_config_name", lambda _: None)

    result = resource_probe.refresh_resource_snapshots()
    assert result["probed"] == 0
    assert result["errors"] == 1
    assert result["running_leases"] == 1
