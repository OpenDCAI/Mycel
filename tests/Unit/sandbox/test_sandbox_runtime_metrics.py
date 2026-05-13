from __future__ import annotations

from types import SimpleNamespace

from backend.sandboxes.runtime.metrics import get_runtime_metrics
from backend.sandboxes.runtime.reads import find_runtime_and_manager


def test_get_runtime_metrics_tolerates_duplicate_session_rows_with_provider_hint() -> None:
    managers = {
        "local": SimpleNamespace(
            provider=SimpleNamespace(
                get_metrics=lambda runtime_id: SimpleNamespace(
                    cpu_percent=1.0,
                    memory_used_mb=2.0,
                    memory_total_mb=3.0,
                    disk_used_gb=4.0,
                    disk_total_gb=5.0,
                    network_rx_kbps=6.0,
                    network_tx_kbps=7.0,
                )
            )
        )
    }
    runtimes = [
        {
            "session_id": "sess-1",
            "thread_id": "thread-1",
            "provider": "local",
            "instance_id": "sess-1",
        },
        {
            "session_id": "sess-1",
            "thread_id": "thread-2",
            "provider": "local",
            "instance_id": "sess-1",
        },
    ]

    result = get_runtime_metrics(
        "sess-1",
        provider_hint="local",
        init_providers_and_managers_fn=lambda: ({}, managers),
        load_all_sandbox_runtimes_fn=lambda _managers: runtimes,
        find_runtime_and_manager_fn=find_runtime_and_manager,
    )

    assert result == {
        "session_id": "sess-1",
        "provider": "local",
        "metrics": {
            "cpu_percent": 1.0,
            "memory_used_mb": 2.0,
            "memory_total_mb": 3.0,
            "disk_used_gb": 4.0,
            "disk_total_gb": 5.0,
            "network_rx_kbps": 6.0,
            "network_tx_kbps": 7.0,
        },
    }
