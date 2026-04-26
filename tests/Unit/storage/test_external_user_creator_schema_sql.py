from pathlib import Path


def test_external_user_creator_schema_source_declares_creator_column() -> None:
    sql = Path("storage/schema/external_user_creator.sql").read_text(encoding="utf-8")

    assert "alter table identity.users" in sql
    assert "created_by_user_id text" in sql
    assert "references identity.users(id)" in sql
    assert "notify pgrst, 'reload schema'" in sql
