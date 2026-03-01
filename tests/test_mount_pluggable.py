"""Mount contract tests for pluggable multi-folder mounts."""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest


def test_mount_spec_defaults_to_mount_mode() -> None:
    from sandbox.config import MountSpec

    mount = MountSpec.model_validate({"source": "/host/x", "target": "/sandbox/x"})
    assert mount.mode == "mount"


def test_create_thread_request_parses_bind_mounts_with_legacy_keys() -> None:
    from backend.web.models.requests import CreateThreadRequest

    payload = CreateThreadRequest.model_validate(
        {
            "sandbox": "local",
            "bind_mounts": [
                {"source": "/host/tasks", "target": "/sandbox/tasks", "mode": "mount", "read_only": False},
                {"host_path": "/host/docs", "mount_path": "/sandbox/docs", "mode": "copy", "read_only": True},
            ],
        }
    )

    assert len(payload.bind_mounts) == 2
    assert payload.bind_mounts[0].source == "/host/tasks"
    assert payload.bind_mounts[0].target == "/sandbox/tasks"
    assert payload.bind_mounts[1].source == "/host/docs"
    assert payload.bind_mounts[1].target == "/sandbox/docs"
    assert payload.bind_mounts[1].mode == "copy"
    assert payload.bind_mounts[1].read_only is True


def test_mount_capability_gate_detects_mismatch() -> None:
    from backend.web.routers.threads import _find_mount_capability_mismatch
    from sandbox.config import MountSpec
    from sandbox.provider import MountCapability

    requested = [MountSpec.model_validate({"source": "/host/a", "target": "/sandbox/a", "mode": "copy"})]
    mismatch = _find_mount_capability_mismatch(
        requested_mounts=requested,
        mount_capability=MountCapability(supports_mount=True, supports_copy=False, supports_read_only=False),
    )

    assert mismatch is not None
    assert mismatch["requested"] == {"mode": "copy", "read_only": False}
    assert mismatch["capability"]["supports_copy"] is False


def test_mount_capability_gate_accepts_supported_combo() -> None:
    from backend.web.routers.threads import _find_mount_capability_mismatch
    from sandbox.config import MountSpec
    from sandbox.provider import MountCapability

    requested = [
        MountSpec.model_validate({"source": "/host/a", "target": "/sandbox/a", "mode": "mount", "read_only": True}),
        MountSpec.model_validate({"source": "/host/b", "target": "/sandbox/b", "mode": "copy", "read_only": False}),
    ]
    mismatch = _find_mount_capability_mismatch(
        requested_mounts=requested,
        mount_capability=MountCapability(supports_mount=True, supports_copy=True, supports_read_only=True),
    )
    assert mismatch is None


def test_mount_capability_gate_respects_mode_handlers() -> None:
    from backend.web.routers.threads import _find_mount_capability_mismatch
    from sandbox.config import MountSpec
    from sandbox.provider import MountCapability

    requested = [MountSpec.model_validate({"source": "/host/a", "target": "/sandbox/a", "mode": "copy"})]
    mismatch = _find_mount_capability_mismatch(
        requested_mounts=requested,
        mount_capability=MountCapability(
            supports_mount=True,
            supports_copy=True,
            supports_read_only=True,
            mode_handlers={"mount": True, "copy": False},
        ),
    )

    assert mismatch is not None
    assert mismatch["requested"] == {"mode": "copy", "read_only": False}
    assert mismatch["capability"]["mode_handlers"]["copy"] is False


def test_docker_provider_supports_multiple_bind_mount_modes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from sandbox.providers.docker import DockerProvider

    copy_source = tmp_path / "bootstrap"
    copy_source.mkdir(parents=True, exist_ok=True)
    (copy_source / "seed.txt").write_text("hello")

    provider = DockerProvider(
        image="python:3.12-slim",
        mount_path="/workspace",
        default_cwd="/home/leon",
        bind_mounts=[
            {"source": "/host/tasks", "target": "/home/leon/shared/tasks", "mode": "mount", "read_only": False},
            {"source": "/host/docs", "target": "/home/leon/shared/docs", "mode": "mount", "read_only": True},
            {"source": str(copy_source), "target": "/home/leon/bootstrap", "mode": "copy", "read_only": False},
            {"host_path": "/host/issues", "mount_path": "/home/leon/shared/issues", "mode": "mount", "read_only": False},
        ],
    )

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="container-123\n", stderr="")

    monkeypatch.setattr(provider, "_run", fake_run)

    session = provider.create_session(context_id="ctx-volume")
    assert session.status == "running"

    run_cmd = calls[0]
    volume_specs = [run_cmd[i + 1] for i, token in enumerate(run_cmd) if token == "-v"]
    assert "/host/tasks:/home/leon/shared/tasks" in volume_specs
    assert "/host/docs:/home/leon/shared/docs:ro" in volume_specs
    assert "/host/issues:/home/leon/shared/issues" in volume_specs
    assert "ctx-volume:/workspace" in volume_specs
    assert all(str(copy_source) not in spec for spec in volume_specs)

    serialized_calls = [" ".join(cmd) for cmd in calls]
    assert any("docker cp" in cmd and "bootstrap/." in cmd and "container-123:/home/leon/bootstrap" in cmd for cmd in serialized_calls)


def test_daytona_provider_maps_multiple_mounts_to_http_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeDaytona:
        def __init__(self) -> None:
            pass

    fake_sdk = types.SimpleNamespace(Daytona=FakeDaytona)
    monkeypatch.setitem(sys.modules, "daytona_sdk", fake_sdk)

    from sandbox.providers.daytona import DaytonaProvider
    import sandbox.providers.daytona as daytona_module

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse(200, {"id": "sb-123"})

    monkeypatch.setattr(daytona_module.httpx, "Client", FakeClient)

    provider = DaytonaProvider(
        api_key="token-1",
        api_url="http://127.0.0.1:3000/api",
        bind_mounts=[
            {"source": "/host/tasks", "target": "/home/daytona/shared/tasks", "mode": "mount", "read_only": False},
            {"source": "/host/docs", "target": "/home/daytona/shared/docs", "mode": "mount", "read_only": True},
            {"source": "/host/bootstrap", "target": "/home/daytona/bootstrap", "mode": "copy", "read_only": False},
            {"host_path": "/host/issues", "mount_path": "/home/daytona/shared/issues", "mode": "mount", "read_only": False},
        ],
    )

    sandbox_id = provider._create_via_http(provider.bind_mounts)
    assert sandbox_id == "sb-123"

    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload.get("bindMounts") == [
        {"hostPath": "/host/tasks", "mountPath": "/home/daytona/shared/tasks", "readOnly": False},
        {"hostPath": "/host/docs", "mountPath": "/home/daytona/shared/docs", "readOnly": True},
        {"hostPath": "/host/issues", "mountPath": "/home/daytona/shared/issues", "readOnly": False},
    ]
