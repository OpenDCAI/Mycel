from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import sandbox_inventory as neutral_sandbox_inventory
from backend import sandbox_recipe_catalog as neutral_sandbox_recipe_catalog
from backend.web.services import sandbox_service
from sandbox.providers.local import LocalSessionProvider


def test_sandbox_provider_availability_owner_moves_out_of_sandbox_service() -> None:
    try:
        neutral_sandbox_provider_availability = importlib.import_module("backend.sandbox_provider_availability")
    except ModuleNotFoundError:
        pytest.fail("backend.sandbox_provider_availability module missing")

    source = inspect.getsource(neutral_sandbox_provider_availability)

    assert "backend.web.services" not in source
    assert "backend.web.core.config" in source


def test_sandbox_inventory_owner_moves_out_of_sandbox_service() -> None:
    source = inspect.getsource(neutral_sandbox_inventory)

    assert "backend.web.services import sandbox_service" not in source
    assert "SandboxConfig" in source


def test_sandbox_service_keeps_sandbox_inventory_compat_surface() -> None:
    source = inspect.getsource(sandbox_service)

    assert "_sandbox_provider_availability.available_sandbox_types(" in source
    assert "sandbox_inventory.init_providers_and_managers()" in source


def test_sandbox_service_keeps_recipe_catalog_compat_surface() -> None:
    source = inspect.getsource(sandbox_service)

    assert "_sandbox_recipe_catalog.list_default_recipes()" in source


def test_sandbox_recipe_catalog_owner_moves_out_of_sandbox_service() -> None:
    source = inspect.getsource(neutral_sandbox_recipe_catalog)

    assert "backend.web.services" not in source
    assert "backend.sandbox_inventory" in source


def test_library_service_uses_neutral_sandbox_provider_availability_owner() -> None:
    from backend.web.services import library_service

    source = inspect.getsource(library_service)

    assert "sandbox_service.available_sandbox_types" not in source
    assert "sandbox_provider_availability.available_sandbox_types" in source


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


def test_available_sandbox_types_marks_e2b_unavailable_when_sdk_missing(monkeypatch, tmp_path: Path) -> None:
    local_provider = LocalSessionProvider(default_cwd=str(tmp_path))
    (tmp_path / "e2b.json").write_text("{}")

    monkeypatch.setattr(sandbox_service, "SANDBOXES_DIR", tmp_path)
    monkeypatch.setattr(
        sandbox_service,
        "init_providers_and_managers",
        lambda: ({"local": local_provider}, {}),
    )
    monkeypatch.setattr(
        sandbox_service.SandboxConfig,
        "load",
        classmethod(lambda cls, name: SimpleNamespace(provider="e2b", name=name)),
    )

    types = sandbox_service.available_sandbox_types()
    e2b = next(item for item in types if item["name"] == "e2b")

    assert e2b["provider"] == "e2b"
    assert e2b["available"] is False
    assert "unavailable in the current process" in e2b["reason"]


def test_build_providers_and_managers_passes_agentbay_pause_capability_overrides(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "agentbay.json").write_text("{}")
    monkeypatch.setattr(sandbox_service, "SANDBOXES_DIR", tmp_path)

    captured: dict[str, object] = {}

    class _FakeAgentBayProvider:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)
            self.name = kwargs["provider_name"]

        def get_capability(self):
            return SimpleNamespace(can_pause=False, can_resume=False, can_destroy=True)

    class _FakeSandboxManager:
        def __init__(self, provider, db_path=None) -> None:
            self.provider = provider
            self.db_path = db_path

    monkeypatch.setattr(sandbox_service, "SandboxManager", _FakeSandboxManager)
    monkeypatch.setattr(
        sandbox_service.SandboxConfig,
        "load",
        classmethod(
            lambda cls, name: SimpleNamespace(
                provider="agentbay",
                agentbay=SimpleNamespace(
                    api_key="test-key",
                    region_id="ap-southeast-1",
                    context_path="/home/wuying",
                    image_id=None,
                    supports_pause=False,
                    supports_resume=False,
                ),
            )
        ),
    )

    import sandbox.providers.agentbay as agentbay_module

    monkeypatch.setattr(agentbay_module, "AgentBayProvider", _FakeAgentBayProvider)

    providers, managers = sandbox_service._build_providers_and_managers()

    assert "agentbay" in providers
    assert "agentbay" in managers
    assert captured["supports_pause"] is False
    assert captured["supports_resume"] is False
