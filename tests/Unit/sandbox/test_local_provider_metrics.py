from __future__ import annotations

import builtins
import io
from types import SimpleNamespace

from sandbox.providers.local import LocalSessionProvider


def test_local_provider_reads_linux_procfs_metrics_without_top_or_free(monkeypatch) -> None:
    provider = LocalSessionProvider()

    cpu_samples = iter(
        [
            "cpu  100 0 100 800 0 0 0 0 0 0\n",
            "cpu  130 0 120 850 0 0 0 0 0 0\n",
        ]
    )

    def fake_open(path: str, *args, **kwargs):
        if path == "/proc/stat":
            return io.StringIO(next(cpu_samples))
        if path == "/proc/meminfo":
            return io.StringIO("MemTotal:       1048576 kB\nMemAvailable:    524288 kB\n")
        raise FileNotFoundError(path)

    monkeypatch.setattr("sandbox.providers.local.platform.system", lambda: "Linux")
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(
        "sandbox.providers.local.os.statvfs",
        lambda _path: SimpleNamespace(f_frsize=4096, f_blocks=262144, f_bavail=131072),
    )

    metrics = provider.get_metrics("host")

    assert metrics is not None
    assert metrics.cpu_percent == 50.0
    assert metrics.memory_total_mb == 1024.0
    assert metrics.memory_used_mb == 512.0
    assert metrics.disk_total_gb == 1.0
    assert metrics.disk_used_gb == 0.5
