"""Unit tests for SQLiteWorkplaceRepo."""
import tempfile
from pathlib import Path

from storage.providers.sqlite.workplace_repo import SQLiteWorkplaceRepo


def test_upsert_and_get():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteWorkplaceRepo(db_path=Path(td) / "test.db")
        repo.upsert("leon", "daytona", "vol-abc", "/workspace/files", "2026-01-01T00:00:00")
        result = repo.get("leon", "daytona")
        assert result is not None
        assert result["member_name"] == "leon"
        assert result["provider_type"] == "daytona"
        assert result["backend_ref"] == "vol-abc"
        assert result["mount_path"] == "/workspace/files"
        repo.close()


def test_upsert_overwrites():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteWorkplaceRepo(db_path=Path(td) / "test.db")
        repo.upsert("leon", "daytona", "vol-old", "/workspace/files", "2026-01-01T00:00:00")
        repo.upsert("leon", "daytona", "vol-new", "/workspace/files", "2026-01-02T00:00:00")
        result = repo.get("leon", "daytona")
        assert result["backend_ref"] == "vol-new"
        repo.close()


def test_list_by_member():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteWorkplaceRepo(db_path=Path(td) / "test.db")
        repo.upsert("leon", "daytona", "vol-1", "/workspace/files", "2026-01-01T00:00:00")
        repo.upsert("leon", "docker", "/home/.leon/workplaces/leon", "/workspace/files", "2026-01-01T00:00:00")
        results = repo.list_by_member("leon")
        assert len(results) == 2
        repo.close()


def test_delete():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteWorkplaceRepo(db_path=Path(td) / "test.db")
        repo.upsert("leon", "daytona", "vol-1", "/workspace/files", "2026-01-01T00:00:00")
        assert repo.delete("leon", "daytona") is True
        assert repo.get("leon", "daytona") is None
        assert repo.delete("leon", "daytona") is False  # already deleted
        repo.close()


def test_delete_all_for_member():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteWorkplaceRepo(db_path=Path(td) / "test.db")
        repo.upsert("leon", "daytona", "vol-1", "/workspace/files", "2026-01-01T00:00:00")
        repo.upsert("leon", "docker", "/path", "/workspace/files", "2026-01-01T00:00:00")
        repo.upsert("other", "daytona", "vol-2", "/workspace/files", "2026-01-01T00:00:00")
        assert repo.delete_all_for_member("leon") == 2
        assert repo.list_by_member("leon") == []
        assert repo.get("other", "daytona") is not None  # other member untouched
        repo.close()


def test_get_nonexistent():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteWorkplaceRepo(db_path=Path(td) / "test.db")
        assert repo.get("nobody", "nothing") is None
        repo.close()
