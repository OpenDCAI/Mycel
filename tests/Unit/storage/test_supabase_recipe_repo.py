from __future__ import annotations

from storage.providers.supabase.recipe_repo import SupabaseRecipeRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_recipe_repo_reads_container_sandbox_recipes() -> None:
    tables = {
        "container.sandbox_recipes": [
            {
                "owner_user_id": "owner-1",
                "recipe_id": "local:default",
                "kind": "custom",
                "provider_type": "local",
                "data_json": '{"id":"local:default"}',
                "created_at": 1000,
                "updated_at": 2000,
            }
        ]
    }
    repo = SupabaseRecipeRepo(FakeSupabaseClient(tables=tables))

    rows = repo.list_by_owner("owner-1")

    assert rows == [
        {
            "owner_user_id": "owner-1",
            "recipe_id": "local:default",
            "kind": "custom",
            "provider_type": "local",
            "data": {"id": "local:default"},
            "created_at": 1000,
            "updated_at": 2000,
        }
    ]
    assert "library_recipes" not in tables


def test_supabase_recipe_repo_writes_container_sandbox_recipes() -> None:
    tables: dict[str, list[dict]] = {"container.sandbox_recipes": []}
    repo = SupabaseRecipeRepo(FakeSupabaseClient(tables=tables))

    row = repo.upsert(
        owner_user_id="owner-1",
        recipe_id="local:default",
        kind="custom",
        provider_type="local",
        data={"id": "local:default"},
        created_at=1000,
    )

    stored = tables["container.sandbox_recipes"][0]
    assert row["recipe_id"] == "local:default"
    assert stored["owner_user_id"] == "owner-1"
    assert stored["data_json"] == '{"id": "local:default"}'
    assert "library_recipes" not in tables
