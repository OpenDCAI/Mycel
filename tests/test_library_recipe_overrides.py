from __future__ import annotations

from pathlib import Path

import pytest

from backend.web.services import library_service


def _builtin_local_recipe() -> list[dict]:
    return [
        {
            "id": "local:default",
            "type": "recipe",
            "name": "Local Default",
            "desc": "Default recipe for local",
            "provider_type": "local",
            "provider_name": "local",
            "features": {"lark_cli": False},
            "configurable_features": {"lark_cli": True},
            "feature_options": [{"key": "lark_cli", "name": "Lark CLI", "description": "desc"}],
            "created_at": 0,
            "updated_at": 0,
            "builtin": True,
        }
    ]


@pytest.fixture()
def isolated_library(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    library_root = tmp_path / "library"
    monkeypatch.setattr(library_service, "LIBRARY_DIR", library_root)
    library_service.ensure_library_dir()
    return library_root


def test_recipe_override_merges_with_builtin(monkeypatch: pytest.MonkeyPatch, isolated_library: Path) -> None:
    monkeypatch.setattr(library_service, "list_default_recipes", _builtin_local_recipe)

    updated = library_service.update_resource(
        "recipe",
        "local:default",
        name="Local Default Edited",
        desc="Edited",
        features={"lark_cli": True},
    )

    assert updated is not None
    assert updated["name"] == "Local Default Edited"
    assert updated["features"] == {"lark_cli": True}

    listed = library_service.list_library("recipe")
    assert listed[0]["name"] == "Local Default Edited"
    assert listed[0]["features"] == {"lark_cli": True}


def test_recipe_delete_resets_to_builtin(monkeypatch: pytest.MonkeyPatch, isolated_library: Path) -> None:
    monkeypatch.setattr(library_service, "list_default_recipes", _builtin_local_recipe)

    library_service.update_resource(
        "recipe",
        "local:default",
        name="Overridden Name",
        features={"lark_cli": True},
    )
    assert library_service.delete_resource("recipe", "local:default") is True

    listed = library_service.list_library("recipe")
    assert listed[0]["name"] == "Local Default"
    assert listed[0]["features"] == {"lark_cli": False}


def test_custom_recipe_lifecycle(monkeypatch: pytest.MonkeyPatch, isolated_library: Path) -> None:
    monkeypatch.setattr(library_service, "list_default_recipes", _builtin_local_recipe)

    created = library_service.create_resource(
        "recipe",
        "Docs With Lark",
        "Shared docs setup",
        "daytona",
        features={"lark_cli": True},
    )

    assert created["name"] == "Docs With Lark"
    assert created["provider_type"] == "daytona"
    assert created["features"] == {"lark_cli": True}
    assert created["builtin"] is False

    listed = library_service.list_library("recipe")
    assert [item["id"] for item in listed] == ["local:default", created["id"]]
    assert listed[1]["name"] == "Docs With Lark"
    assert listed[1]["provider_type"] == "daytona"
    assert library_service.delete_resource("recipe", created["id"]) is True
    listed_after_delete = library_service.list_library("recipe")
    assert [item["id"] for item in listed_after_delete] == ["local:default"]
