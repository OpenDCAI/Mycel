from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sandbox import resource_snapshot
from tests.fakes.supabase import FakeSupabaseClient


class _FakeProvider:
    def get_metrics(self, instance_id: str):
        assert instance_id == "instance-1"
        return SimpleNamespace(
            cpu_percent=12.5,
            memory_used_mb=512.0,
            memory_total_mb=1024.0,
            disk_used_gb=5.0,
            disk_total_gb=20.0,
            network_rx_kbps=3.0,
            network_tx_kbps=4.0,
        )


def test_ensure_resource_snapshot_table_is_noop_for_supabase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")

    db_path = tmp_path / "sandbox.db"
    resource_snapshot.ensure_resource_snapshot_table(db_path)

    assert not db_path.exists()


def test_probe_and_upsert_for_instance_avoids_sqlite_writes_for_supabase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    client = FakeSupabaseClient(tables={"lease_resource_snapshots": []})
    monkeypatch.setattr(resource_snapshot._storage_factory, "_supabase_client", lambda: client)
    db_path = tmp_path / "sandbox.db"

    result = resource_snapshot.probe_and_upsert_for_instance(
        lease_id="lease-1",
        provider_name="local",
        observed_state="running",
        probe_mode="running_runtime",
        provider=_FakeProvider(),
        instance_id="instance-1",
        db_path=db_path,
    )

    assert result == {"ok": True, "error": None}
    assert not db_path.exists()
    rows = client._tables["lease_resource_snapshots"]
    assert len(rows) == 1
    assert rows[0]["lease_id"] == "lease-1"
