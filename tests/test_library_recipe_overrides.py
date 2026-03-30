from __future__ import annotations

from pathlib import Path

import pytest

from backend.web.services import library_service


@pytest.fixture()
def isolated_library(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    library_root = tmp_path / "library"
    monkeypatch.setattr(library_service, "LIBRARY_DIR", library_root)
    library_service.ensure_library_dir()
    return library_root


def test_recipe_override_merges_with_builtin(monkeypatch: pytest.MonkeyPatch, isolated_library: Path) -> None:
    monkeypatch.setattr(
        library_service,
        "list_default_recipes",
        lambda: [
            {
                "id": "local:default",
                "type": "recipe",
                "name": "Local Default",
                "desc": "Default recipe for local",
                "provider_name": "local",
                "provider_type": "local",
                "features": {"lark_cli": False},
                "configurable_features": {"lark_cli": True},
                "feature_options": [{"key": "lark_cli", "name": "Lark CLI", "description": "desc"}],
                "created_at": 0,
                "updated_at": 0,
            }
        ],
    )

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
    monkeypatch.setattr(
        library_service,
        "list_default_recipes",
        lambda: [
            {
                "id": "local:default",
                "type": "recipe",
                "name": "Local Default",
                "desc": "Default recipe for local",
                "provider_name": "local",
                "provider_type": "local",
                "features": {"lark_cli": False},
                "configurable_features": {"lark_cli": True},
                "feature_options": [{"key": "lark_cli", "name": "Lark CLI", "description": "desc"}],
                "created_at": 0,
                "updated_at": 0,
            }
        ],
    )

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


def test_create_custom_recipe_and_list_with_builtins(monkeypatch: pytest.MonkeyPatch, isolated_library: Path) -> None:
    monkeypatch.setattr(
        library_service,
        "list_default_recipes",
        lambda: [
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
        ],
    )

    created = library_service.create_resource("recipe", "Daytona Docs", "Shared docs setup", "daytona")

    assert created["name"] == "Daytona Docs"
    assert created["provider_type"] == "daytona"
    assert created["builtin"] is False

    listed = library_service.list_library("recipe")
    assert [item["id"] for item in listed] == ["local:default", created["id"]]
    assert listed[1]["name"] == "Daytona Docs"
    assert listed[1]["provider_type"] == "daytona"


def test_delete_custom_recipe_removes_it(monkeypatch: pytest.MonkeyPatch, isolated_library: Path) -> None:
    monkeypatch.setattr(library_service, "list_default_recipes", lambda: [])

    created = library_service.create_resource("recipe", "Daytona Docs", "Shared docs setup", "daytona")

    assert library_service.delete_resource("recipe", created["id"]) is True
    assert library_service.list_library("recipe") == []


def test_create_custom_recipe_preserves_selected_features(monkeypatch: pytest.MonkeyPatch, isolated_library: Path) -> None:
    monkeypatch.setattr(library_service, "list_default_recipes", lambda: [])

    created = library_service.create_resource(
        "recipe",
        "Docs With Lark",
        "Shared docs setup",
        "daytona",
        features={"lark_cli": True},
    )

    assert created["provider_type"] == "daytona"
    assert created["features"] == {"lark_cli": True}

    listed = library_service.list_library("recipe")
    assert listed == [created]
