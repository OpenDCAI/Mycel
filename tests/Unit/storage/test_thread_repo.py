import sqlite3

import pytest

from storage.contracts import MemberRow, MemberType
from storage.providers.sqlite.member_repo import SQLiteMemberRepo
from storage.providers.sqlite.thread_repo import SQLiteThreadRepo


def test_create_main_thread_persists_main_flag(tmp_path):
    db_path = tmp_path / "leon.db"
    repo = SQLiteThreadRepo(db_path)
    try:
        repo.create(
            thread_id="agent-1",
            member_id="member-1",
            sandbox_type="local",
            created_at=1.0,
            is_main=True,
            branch_index=0,
        )

        row = repo.get_by_id("agent-1")
        assert row is not None
        assert row["is_main"] is True
        assert row["branch_index"] == 0
        assert repo.get_main_thread("member-1")["id"] == "agent-1"
    finally:
        repo.close()


def test_rejects_multiple_main_threads_for_same_member(tmp_path):
    db_path = tmp_path / "leon.db"
    repo = SQLiteThreadRepo(db_path)
    try:
        repo.create(
            thread_id="agent-1",
            member_id="member-1",
            sandbox_type="local",
            created_at=1.0,
            is_main=True,
            branch_index=0,
        )

        with pytest.raises(sqlite3.IntegrityError):
            repo.create(
                thread_id="agent-2",
                member_id="member-1",
                sandbox_type="local",
                created_at=2.0,
                is_main=True,
                branch_index=0,
            )
    finally:
        repo.close()


def test_rejects_duplicate_branch_index_for_same_member(tmp_path):
    db_path = tmp_path / "leon.db"
    repo = SQLiteThreadRepo(db_path)
    try:
        repo.create(
            thread_id="agent-1",
            member_id="member-1",
            sandbox_type="local",
            created_at=1.0,
            is_main=True,
            branch_index=0,
        )

        repo.create(
            thread_id="agent-2",
            member_id="member-1",
            sandbox_type="local",
            created_at=2.0,
            is_main=False,
            branch_index=1,
        )

        with pytest.raises(sqlite3.IntegrityError):
            repo.create(
                thread_id="agent-3",
                member_id="member-1",
                sandbox_type="local",
                created_at=3.0,
                is_main=False,
                branch_index=1,
            )
    finally:
        repo.close()


def test_list_by_owner_user_id_includes_main_flag(tmp_path):
    db_path = tmp_path / "leon.db"
    member_repo = SQLiteMemberRepo(db_path)
    thread_repo = SQLiteThreadRepo(db_path)
    try:
        member_repo.create(
            MemberRow(
                id="owner-1",
                name="owner",
                type=MemberType.HUMAN,
                created_at=1.0,
            )
        )
        member_repo.create(
            MemberRow(
                id="member-1",
                name="Toad",
                type=MemberType.MYCEL_AGENT,
                owner_user_id="owner-1",
                created_at=2.0,
            )
        )
        thread_repo.create(
            thread_id="agent-1",
            member_id="member-1",
            sandbox_type="local",
            created_at=3.0,
            is_main=True,
            branch_index=0,
        )

        rows = thread_repo.list_by_owner_user_id("owner-1")
        assert len(rows) == 1
        assert rows[0]["is_main"] is True
        assert rows[0]["branch_index"] == 0
    finally:
        thread_repo.close()
        member_repo.close()
