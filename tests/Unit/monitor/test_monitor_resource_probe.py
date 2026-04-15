from unittest.mock import MagicMock

import pytest

from backend.web.services import resource_service
from sandbox import resource_snapshot
from storage import runtime as storage_runtime


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


class _FakeSandboxSnapshotRepo:
    def __init__(self) -> None:
        self.upserts: list[dict] = []

    def close(self) -> None:
        return None

    def upsert_resource_snapshot_for_sandbox(self, **kwargs):
        self.upserts.append(kwargs)


def test_upsert_resource_snapshot_for_sandbox_requires_repo_sandbox_wrapper(monkeypatch) -> None:
    repo = _FakeSnapshotRepo()
    monkeypatch.setattr(storage_runtime, "build_resource_snapshot_repo", lambda **_kwargs: repo)

    with pytest.raises(RuntimeError, match="sandbox-shaped snapshot repo write requires upsert_resource_snapshot_for_sandbox"):
        storage_runtime.upsert_resource_snapshot_for_sandbox(
            sandbox_id="sandbox-1",
            provider_name="p1",
            observed_state="detached",
            probe_mode="running_runtime",
        )


def test_upsert_resource_snapshot_for_sandbox_no_longer_requires_legacy_lease_bridge(monkeypatch) -> None:
    repo = _FakeSandboxSnapshotRepo()
    monkeypatch.setattr(storage_runtime, "build_resource_snapshot_repo", lambda **_kwargs: repo)

    storage_runtime.upsert_resource_snapshot_for_sandbox(
        sandbox_id="sandbox-1",
        provider_name="p1",
        observed_state="detached",
        probe_mode="running_runtime",
    )

    assert repo.upserts == [
        {
            "sandbox_id": "sandbox-1",
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
            "probe_error": None,
        }
    ]


def test_resource_snapshot_adapter_no_longer_exposes_lease_shaped_write_shell() -> None:
    adapter = resource_service._SandboxSnapshotRepoAdapter(sandbox_id="sandbox-1")

    assert not hasattr(adapter, "upsert_lease_resource_snapshot")


def test_resource_snapshot_module_no_longer_exposes_lease_shaped_write_helper() -> None:
    assert not hasattr(resource_snapshot, "upsert_lease_resource_snapshot")
    assert not hasattr(resource_snapshot, "_upsert_lease_resource_snapshot")


def test_probe_and_upsert_for_instance_accepts_sandbox_shaped_repo() -> None:
    repo = _FakeSandboxSnapshotRepo()

    result = resource_snapshot.probe_and_upsert_for_instance(
        sandbox_id="sandbox-1",
        lease_id="lease-1",
        provider_name="p1",
        observed_state="detached",
        probe_mode="running_runtime",
        provider=_FakeProvider(),
        instance_id="instance-1",
        repo=repo,
    )

    assert result == {"ok": False, "error": "metrics unavailable"}
    assert repo.upserts == [
        {
            "sandbox_id": "sandbox-1",
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


def test_probe_and_upsert_for_instance_without_repo_prefers_sandbox_shaped_helper(monkeypatch) -> None:
    captured: list[dict] = []

    def _fake_upsert_resource_snapshot_for_sandbox(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(resource_snapshot, "upsert_resource_snapshot_for_sandbox", _fake_upsert_resource_snapshot_for_sandbox)

    result = resource_snapshot.probe_and_upsert_for_instance(
        sandbox_id="sandbox-1",
        lease_id="lease-1",
        provider_name="p1",
        observed_state="detached",
        probe_mode="running_runtime",
        provider=_FakeProvider(),
        instance_id="instance-1",
        repo=None,
    )

    assert result == {"ok": False, "error": "metrics unavailable"}
    assert captured == [
        {
            "sandbox_id": "sandbox-1",
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


def test_probe_and_upsert_for_instance_requires_sandbox_id() -> None:
    result = resource_snapshot.probe_and_upsert_for_instance(
        lease_id="lease-1",
        provider_name="p1",
        observed_state="detached",
        probe_mode="running_runtime",
        provider=_FakeProvider(),
        instance_id="instance-1",
        repo=None,
    )

    assert result == {"ok": False, "error": "sandbox-shaped snapshot helper requires sandbox_id"}


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
    assert {call["sandbox_id"] for call in calls} == {"sandbox-1"}
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
