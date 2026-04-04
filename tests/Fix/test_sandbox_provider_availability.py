from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.web.services import sandbox_service
from sandbox.providers.local import LocalSessionProvider


def test_available_sandbox_types_marks_configured_but_unavailable_provider(monkeypatch, tmp_path: Path) -> None:
    local_provider = LocalSessionProvider(default_cwd=str(tmp_path))
    (tmp_path / "daytona.json").write_text("{}")

    monkeypatch.setattr(sandbox_service, "SANDBOXES_DIR", tmp_path)
    monkeypatch.setattr(
        sandbox_service,
        "init_providers_and_managers",
        lambda: ({"local": local_provider}, {}),
    )
    monkeypatch.setattr(
        sandbox_service.SandboxConfig,
        "load",
        classmethod(lambda cls, name: SimpleNamespace(provider="daytona", name=name)),
    )

    types = sandbox_service.available_sandbox_types()
    daytona = next(item for item in types if item["name"] == "daytona")

    assert daytona["provider"] == "daytona"
    assert daytona["available"] is False
    assert "unavailable in the current process" in daytona["reason"]
