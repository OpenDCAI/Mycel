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


class _FakeSnapshotRepo:
    def __init__(self) -> None:
        self.upserts: list[dict] = []

    def close(self) -> None:
        return None

    def upsert_lease_resource_snapshot(self, **kwargs):
        self.upserts.append(kwargs)


def test_refresh_resource_snapshots_routes_successful_probe_through_sandbox_wrapper(monkeypatch):
    monkeypatch.setattr(
        resource_service,
        "make_sandbox_monitor_repo",
        lambda: _make_probe_repo(
            [
                {
                    "provider_name": "p1",
                    "instance_id": "s-1",
                    "sandbox_id": "sandbox-1",
                    "legacy_lease_id": "l-1",
                    "observed_state": "detached",
                },
            ]
        ),
    )
    monkeypatch.setattr(resource_service, "build_provider_from_config_name", lambda _: _FakeProvider())

    captured: list[dict] = []

    def _fake_upsert_resource_snapshot_for_sandbox(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(resource_service, "upsert_resource_snapshot_for_sandbox", _fake_upsert_resource_snapshot_for_sandbox)

    result = resource_service.refresh_resource_snapshots()

    assert result["probed"] == 1
    assert result["errors"] == 1
    assert captured == [
        {
            "sandbox_id": "sandbox-1",
            "legacy_lease_id": "l-1",
            "provider_name": "p1",
            "observed_state": "detached",
            "probe_mode": "running_runtime",
            "cpu_used": None,
            "cpu_limit": None,
            "memory_used_mb": None,
            "memory_total_mb": None,
            "disk_used_gb": None,
            "disk_total_gb": None,
            "network_rx_kbps": None,
            "network_tx_kbps": None,
            "probe_error": "metrics unavailable",
        }
    ]


def test_refresh_resource_snapshots_skips_paused_leases(monkeypatch):
    monkeypatch.setattr(
        resource_service,
        "make_sandbox_monitor_repo",
        lambda: _make_probe_repo(
            [
                {
                    "provider_name": "p1",
                    "instance_id": "s-1",
                    "sandbox_id": "sandbox-1",
                    "legacy_lease_id": "l-1",
                    "observed_state": "detached",
                },
                {
                    "provider_name": "p1",
                    "instance_id": "s-2",
                    "sandbox_id": "sandbox-2",
                    "legacy_lease_id": "l-2",
                    "observed_state": "paused",
                },
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
    assert result["probed"] == 1
    assert result["errors"] == 0
    assert result["running_targets"] == 1
    assert result["non_running_targets"] == 0
    assert {call["lease_id"] for call in calls} == {"l-1"}
    assert {call["probe_mode"] for call in calls} == {"running_runtime"}


def test_refresh_resource_snapshots_counts_provider_build_error(monkeypatch):
    monkeypatch.setattr(
        resource_service,
        "make_sandbox_monitor_repo",
        lambda: _make_probe_repo(
            [
                {
                    "provider_name": "p-missing",
                    "instance_id": "s-1",
                    "sandbox_id": "sandbox-1",
                    "legacy_lease_id": "l-1",
                    "observed_state": "detached",
                },
            ]
        ),
    )
    monkeypatch.setattr(resource_service, "build_provider_from_config_name", lambda _: None)
    captured: list[dict] = []

    def _fake_upsert_resource_snapshot_for_sandbox(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(resource_service, "upsert_resource_snapshot_for_sandbox", _fake_upsert_resource_snapshot_for_sandbox)

    result = resource_service.refresh_resource_snapshots()
    assert result["probed"] == 0
    assert result["errors"] == 1
    assert result["running_targets"] == 1
    assert result["non_running_targets"] == 0
    assert captured == [
        {
            "sandbox_id": "sandbox-1",
            "legacy_lease_id": "l-1",
            "provider_name": "p-missing",
            "observed_state": "detached",
            "probe_mode": "running_runtime",
            "probe_error": "provider init failed: p-missing",
        }
    ]


def test_refresh_resource_snapshots_skips_paused_provider_build_error(monkeypatch):
    monkeypatch.setattr(
        resource_service,
        "make_sandbox_monitor_repo",
        lambda: _make_probe_repo(
            [
                {
                    "provider_name": "p-missing",
                    "instance_id": "s-1",
                    "sandbox_id": "sandbox-1",
                    "legacy_lease_id": "l-1",
                    "observed_state": "paused",
                },
            ]
        ),
    )
    monkeypatch.setattr(resource_service, "build_provider_from_config_name", lambda _: None)

    captured: list[dict] = []

    def _fake_upsert_resource_snapshot_for_sandbox(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(resource_service, "upsert_resource_snapshot_for_sandbox", _fake_upsert_resource_snapshot_for_sandbox)

    result = resource_service.refresh_resource_snapshots()

    assert result["probed"] == 0
    assert result["errors"] == 0
    assert result["running_targets"] == 0
    assert result["non_running_targets"] == 0
    assert captured == []
