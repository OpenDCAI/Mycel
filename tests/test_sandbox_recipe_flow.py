from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.web.models.requests import CreateThreadRequest
from backend.web.routers import threads as threads_router
from backend.web.services import library_service, sandbox_service
from sandbox.recipes import list_builtin_recipes
from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
from storage.contracts import MemberRow, MemberType
from storage.providers.sqlite.member_repo import SQLiteMemberRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo
from storage.providers.sqlite.thread_repo import SQLiteThreadRepo


def _patch_sandbox_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    main_db = tmp_path / "leon.db"
    sandbox_db = tmp_path / "sandbox.db"
    volumes_root = tmp_path / "volumes"
    volumes_root.mkdir(parents=True, exist_ok=True)

    import backend.web.core.config as web_config

    monkeypatch.setenv("LEON_DB_PATH", str(main_db))
    monkeypatch.setenv("LEON_SANDBOX_DB_PATH", str(sandbox_db))
    monkeypatch.setattr(web_config, "SANDBOX_VOLUME_ROOT", volumes_root)
    return sandbox_db


def _make_app(member_repo: SQLiteMemberRepo, thread_repo: SQLiteThreadRepo) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            member_repo=member_repo,
            entity_repo=SimpleNamespace(create=lambda *_args, **_kwargs: None),
            thread_repo=thread_repo,
            thread_sandbox={},
            thread_cwd={},
        )
    )


def test_builtin_recipes_dedupe_provider_variants_and_only_expose_defaults() -> None:
    items = list_builtin_recipes([
        {
            "name": "local",
            "available": True,
            "capability": {"runtime_kind": "local"},
        },
        {
            "name": "daytona",
            "available": True,
            "provider": "daytona",
            "capability": {"runtime_kind": "remote"},
        },
        {
            "name": "daytona_selfhost",
            "available": True,
            "provider": "daytona",
            "capability": {"runtime_kind": "remote"},
        },
    ])

    assert [item["id"] for item in items] == ["local:default", "daytona:default"]
    assert items[0]["provider_type"] == "local"
    assert items[0]["features"] == {"lark_cli": False}
    assert items[0]["configurable_features"] == {"lark_cli": True}
    assert items[0]["feature_options"][0]["key"] == "lark_cli"
    assert items[1]["provider_type"] == "daytona"


def test_create_thread_can_reuse_existing_lease(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox_db = _patch_sandbox_paths(monkeypatch, tmp_path)
    main_db = tmp_path / "leon.db"

    member_repo = SQLiteMemberRepo(main_db)
    thread_repo = SQLiteThreadRepo(main_db)

    member_repo.create(MemberRow(
        id="user-1",
        name="owner",
        type=MemberType.HUMAN,
        created_at=1.0,
    ))
    member_repo.create(MemberRow(
        id="member-1",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="user-1",
        created_at=2.0,
    ))

    app = _make_app(member_repo, thread_repo)

    first = threads_router._create_owned_thread(
        app,
        "user-1",
        CreateThreadRequest(member_id="member-1", sandbox="local"),
        is_main=False,
    )

    terminal_repo = SQLiteTerminalRepo(db_path=sandbox_db)
    lease_repo = SQLiteLeaseRepo(db_path=sandbox_db)
    shared_terminal = terminal_repo.get_active(first["thread_id"])
    assert shared_terminal is not None
    shared_lease_id = str(shared_terminal["lease_id"])
    assert len(lease_repo.list_all()) == 1

    second = threads_router._create_owned_thread(
        app,
        "user-1",
        CreateThreadRequest(member_id="member-1", lease_id=shared_lease_id),
        is_main=False,
    )

    second_terminal = terminal_repo.get_active(second["thread_id"])
    assert second_terminal is not None
    assert str(second_terminal["lease_id"]) == shared_lease_id
    assert len(lease_repo.list_all()) == 1


def test_list_user_leases_only_returns_owned_leases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox_db = _patch_sandbox_paths(monkeypatch, tmp_path)
    main_db = tmp_path / "leon.db"

    member_repo = SQLiteMemberRepo(main_db)
    thread_repo = SQLiteThreadRepo(main_db)

    member_repo.create(MemberRow(
        id="user-1",
        name="owner-1",
        type=MemberType.HUMAN,
        created_at=1.0,
    ))
    member_repo.create(MemberRow(
        id="user-2",
        name="owner-2",
        type=MemberType.HUMAN,
        created_at=2.0,
    ))
    member_repo.create(MemberRow(
        id="member-1",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        avatar="uploaded",
        owner_user_id="user-1",
        created_at=3.0,
    ))
    member_repo.create(MemberRow(
        id="member-2",
        name="Morel",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="user-2",
        created_at=4.0,
    ))

    app = _make_app(member_repo, thread_repo)

    owned = threads_router._create_owned_thread(
        app,
        "user-1",
        CreateThreadRequest(member_id="member-1", sandbox="local"),
        is_main=False,
    )
    threads_router._create_owned_thread(
        app,
        "user-2",
        CreateThreadRequest(member_id="member-2", sandbox="local"),
        is_main=False,
    )

    leases = sandbox_service.list_user_leases("user-1", main_db_path=main_db, sandbox_db_path=sandbox_db)

    assert len(leases) == 1
    assert leases[0]["provider_name"] == "local"
    assert leases[0]["thread_ids"] == [owned["thread_id"]]
    assert [agent["member_id"] for agent in leases[0]["agents"]] == ["member-1"]
    assert leases[0]["agents"][0]["avatar_url"] == "/api/members/member-1/avatar"


def test_create_thread_persists_selected_recipe_snapshot_on_lease(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox_db = _patch_sandbox_paths(monkeypatch, tmp_path)
    main_db = tmp_path / "leon.db"

    member_repo = SQLiteMemberRepo(main_db)
    thread_repo = SQLiteThreadRepo(main_db)

    member_repo.create(MemberRow(
        id="user-1",
        name="owner",
        type=MemberType.HUMAN,
        created_at=1.0,
    ))
    member_repo.create(MemberRow(
        id="member-1",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="user-1",
        created_at=2.0,
    ))

    app = _make_app(member_repo, thread_repo)

    threads_router._create_owned_thread(
        app,
        "user-1",
        CreateThreadRequest(
            member_id="member-1",
            sandbox="local",
            recipe={
                "id": "local:default",
                "name": "Local Default",
                "provider_name": "local",
                "provider_type": "local",
                "features": {"lark_cli": True},
            },
        ),
        is_main=False,
    )

    leases = sandbox_service.list_user_leases("user-1", main_db_path=main_db, sandbox_db_path=sandbox_db)

    assert len(leases) == 1
    assert leases[0]["recipe_id"] == "local:default"
    assert leases[0]["recipe_name"] == "Local Default"
    assert leases[0]["recipe"]["features"] == {"lark_cli": True}


def test_daytona_provider_config_uses_daytona_type_recipe_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox_db = _patch_sandbox_paths(monkeypatch, tmp_path)
    main_db = tmp_path / "leon.db"

    member_repo = SQLiteMemberRepo(main_db)
    thread_repo = SQLiteThreadRepo(main_db)

    member_repo.create(MemberRow(
        id="user-1",
        name="owner",
        type=MemberType.HUMAN,
        created_at=1.0,
    ))
    member_repo.create(MemberRow(
        id="member-1",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="user-1",
        created_at=2.0,
    ))

    app = _make_app(member_repo, thread_repo)

    threads_router._create_owned_thread(
        app,
        "user-1",
        CreateThreadRequest(
            member_id="member-1",
            sandbox="daytona_selfhost",
            recipe={
                "id": "daytona:default",
                "name": "Daytona Default",
                "provider_type": "daytona",
                "features": {"lark_cli": False},
            },
        ),
        is_main=False,
    )

    leases = sandbox_service.list_user_leases("user-1", main_db_path=main_db, sandbox_db_path=sandbox_db)

    assert len(leases) == 1
    assert leases[0]["provider_name"] == "daytona_selfhost"
    assert leases[0]["recipe_id"] == "daytona:default"
    assert leases[0]["recipe"]["provider_type"] == "daytona"
