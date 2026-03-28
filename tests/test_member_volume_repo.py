"""Unit tests for SQLiteMemberVolumeRepo."""
import tempfile
from pathlib import Path

from storage.providers.sqlite.member_volume_repo import SQLiteMemberVolumeRepo


def test_upsert_and_get():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteMemberVolumeRepo(db_path=Path(td) / "test.db")
        repo.upsert("m_abc123", "daytona", "vol-abc", "/workspace/files", "2026-01-01T00:00:00")
        result = repo.get("m_abc123", "daytona")
        assert result is not None
        assert result["member_id"] == "m_abc123"
        assert result["provider_type"] == "daytona"
        assert result["backend_ref"] == "vol-abc"
        assert result["mount_path"] == "/workspace/files"
        repo.close()


def test_upsert_overwrites():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteMemberVolumeRepo(db_path=Path(td) / "test.db")
        repo.upsert("m_abc123", "daytona", "vol-old", "/workspace/files", "2026-01-01T00:00:00")
        repo.upsert("m_abc123", "daytona", "vol-new", "/workspace/files", "2026-01-02T00:00:00")
        result = repo.get("m_abc123", "daytona")
        assert result["backend_ref"] == "vol-new"
        repo.close()


def test_list_by_member():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteMemberVolumeRepo(db_path=Path(td) / "test.db")
        repo.upsert("m_abc123", "daytona", "vol-1", "/workspace/files", "2026-01-01T00:00:00")
        repo.upsert("m_abc123", "docker", "/home/.leon/volumes/leon", "/workspace/files", "2026-01-01T00:00:00")
        results = repo.list_by_member("m_abc123")
        assert len(results) == 2
        repo.close()


def test_delete():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteMemberVolumeRepo(db_path=Path(td) / "test.db")
        repo.upsert("m_abc123", "daytona", "vol-1", "/workspace/files", "2026-01-01T00:00:00")
        assert repo.delete("m_abc123", "daytona") is True
        assert repo.get("m_abc123", "daytona") is None
        assert repo.delete("m_abc123", "daytona") is False  # already deleted
        repo.close()


def test_delete_all_for_member():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteMemberVolumeRepo(db_path=Path(td) / "test.db")
        repo.upsert("m_abc123", "daytona", "vol-1", "/workspace/files", "2026-01-01T00:00:00")
        repo.upsert("m_abc123", "docker", "/path", "/workspace/files", "2026-01-01T00:00:00")
        repo.upsert("m_other", "daytona", "vol-2", "/workspace/files", "2026-01-01T00:00:00")
        assert repo.delete_all_for_member("m_abc123") == 2
        assert repo.list_by_member("m_abc123") == []
        assert repo.get("m_other", "daytona") is not None  # other member untouched
        repo.close()


def test_get_nonexistent():
    with tempfile.TemporaryDirectory() as td:
        repo = SQLiteMemberVolumeRepo(db_path=Path(td) / "test.db")
        assert repo.get("nobody", "nothing") is None
        repo.close()
