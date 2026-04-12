from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from backend.web.services import library_service, thread_launch_config_service


class _RecipeRepo:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = {row["recipe_id"]: row for row in rows or []}
        self.upserts: list[dict] = []

    def list_by_owner(self, owner_user_id: str) -> list[dict]:
        return [row for row in self.rows.values() if row["owner_user_id"] == owner_user_id]

    def get(self, owner_user_id: str, recipe_id: str) -> dict | None:
        row = self.rows.get(recipe_id)
        if row is None or row["owner_user_id"] != owner_user_id:
            return None
        return row

    def upsert(
        self,
        *,
        owner_user_id: str,
        recipe_id: str,
        kind: str,
        provider_type: str,
        data: dict,
        created_at: int | None = None,
    ) -> dict:
        row = {
            "owner_user_id": owner_user_id,
            "recipe_id": recipe_id,
            "kind": kind,
            "provider_type": provider_type,
            "data": data,
            "created_at": created_at or data.get("created_at", 0),
            "updated_at": data.get("updated_at", 0),
        }
        self.rows[recipe_id] = row
        self.upserts.append(row)
        return row


def test_recipe_library_is_repo_backed_and_seed_preserves_provider_config_identity() -> None:
    repo = _RecipeRepo()

    library_service.seed_default_recipes(
        "owner-1",
        recipe_repo=repo,
        sandbox_types=[
            {"name": "local", "provider": "local", "available": True},
            {"name": "daytona", "provider": "daytona", "available": True},
            {"name": "daytona_selfhost", "provider": "daytona", "available": True},
        ],
    )

    with patch.object(library_service.sandbox_service, "list_default_recipes", side_effect=AssertionError("recipe list must be repo-backed")):
        items = library_service.list_library("recipe", owner_user_id="owner-1", recipe_repo=repo)

    assert [item["id"] for item in items] == ["daytona:default", "daytona_selfhost:default", "local:default"]
    assert [item["provider_name"] for item in items] == ["daytona", "daytona_selfhost", "local"]
    assert [item["provider_type"] for item in items] == ["daytona", "daytona", "local"]


def test_derived_thread_launch_config_matches_recipe_by_provider_name_not_provider_type() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_launch_pref_repo=SimpleNamespace(get=lambda _owner_user_id, _agent_user_id: {}),
            thread_repo=SimpleNamespace(list_by_agent_user=lambda _agent_user_id: []),
            user_repo=SimpleNamespace(),
            recipe_repo=object(),
        )
    )

    with (
        patch.object(thread_launch_config_service.sandbox_service, "list_user_leases", return_value=[]),
        patch.object(
            thread_launch_config_service.sandbox_service,
            "available_sandbox_types",
            return_value=[
                {"name": "daytona_selfhost", "provider": "daytona", "available": True},
                {"name": "daytona", "provider": "daytona", "available": True},
            ],
        ),
        patch.object(
            thread_launch_config_service,
            "list_library",
            return_value=[
                {
                    "id": "daytona:default",
                    "name": "Daytona SaaS",
                    "provider_name": "daytona",
                    "provider_type": "daytona",
                    "available": True,
                    "features": {},
                },
                {
                    "id": "daytona_selfhost:default",
                    "name": "Self-host Daytona",
                    "provider_name": "daytona_selfhost",
                    "provider_type": "daytona",
                    "available": True,
                    "features": {},
                },
            ],
        ),
    ):
        result = thread_launch_config_service.resolve_default_config(app, "owner-1", "agent-1")

    assert result["config"]["provider_config"] == "daytona_selfhost"
    assert result["config"]["recipe"]["id"] == "daytona_selfhost:default"
