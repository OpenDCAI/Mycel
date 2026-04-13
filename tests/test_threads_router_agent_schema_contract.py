from __future__ import annotations

from types import SimpleNamespace

from backend.web.models.requests import CreateThreadRequest
from backend.web.routers import threads as threads_router


class _MemberRepo:
    def __init__(self) -> None:
        self._seq = 0

    def get_by_id(self, member_id: str):
        if member_id != "agent_1":
            return None
        return SimpleNamespace(id="agent_1", owner_user_id="owner_1", name="Builder", avatar=None)

    def increment_entity_seq(self, member_id: str) -> int:
        assert member_id == "agent_1"
        self._seq += 1
        return self._seq


class _ThreadRepo:
    def __init__(self) -> None:
        self.created: dict | None = None

    def get_main_thread(self, member_id: str):
        assert member_id == "agent_1"
        return None

    def get_next_branch_index(self, member_id: str) -> int:
        assert member_id == "agent_1"
        return 1

    def create(self, **kwargs):
        self.created = dict(kwargs)


class _EntityRepo:
    def __init__(self) -> None:
        self.created = None

    def get_by_id(self, entity_id: str):
        assert entity_id == "agent_1"
        return None

    def create(self, row) -> None:
        self.created = row


class _ThreadLaunchPrefRepo:
    def save_successful(self, *_args, **_kwargs) -> None:
        return None


def test_create_owned_thread_passes_owner_user_id_to_thread_repo() -> None:
    thread_repo = _ThreadRepo()
    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=_MemberRepo(),
            entity_repo=_EntityRepo(),
            thread_repo=thread_repo,
            thread_launch_pref_repo=_ThreadLaunchPrefRepo(),
            thread_sandbox={},
            thread_cwd={},
        )
    )

    threads_router._create_owned_thread(
        app,
        "owner_1",
        CreateThreadRequest(member_id="agent_1", sandbox="local"),
        is_main=False,
    )

    assert thread_repo.created is not None
    assert thread_repo.created["owner_user_id"] == "owner_1"
