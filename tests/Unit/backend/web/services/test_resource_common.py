import pytest

from backend.web.services import resource_common


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

    def list_by_ids(self, thread_ids: list[str]):
        return [
            {"id": thread_id, **row}
            for thread_id, row in self._rows.items()
            if thread_id in set(thread_ids)
        ]

    def close(self):
        pass


class _FakeAgent:
    def __init__(self, user_id: str, display_name: str, avatar: str | None = None):
        self.id = user_id
        self.display_name = display_name
        self.avatar = avatar


class _FakeUserRepo:
    def __init__(self, users):
        self._users = users

    def list_all(self):
        return list(self._users)

    def close(self):
        pass


@pytest.mark.parametrize(
    ("thread_repo", "expected_thread_ids"),
    [
        (_FakeThreadRepo({"thread-1": {"agent_user_id": "agent-1"}}), ["thread-1", "thread-2"]),
    ],
)
def test_thread_owners_resolve_runtime_storage_metadata(thread_repo, expected_thread_ids):
    owners = resource_common.thread_owners(
        expected_thread_ids,
        thread_repo=thread_repo,
        user_repo=_FakeUserRepo([_FakeAgent("agent-1", "Toad", avatar="x")]),
    )

    assert owners == {
        "thread-1": {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": "/api/users/agent-1/avatar"},
        "thread-2": {"agent_user_id": None, "agent_name": "未绑定Agent", "avatar_url": None},
    }


def test_thread_owners_prefers_batch_thread_lookup() -> None:
    class _BatchOnlyThreadRepo:
        def list_by_ids(self, thread_ids: list[str]):
            assert thread_ids == ["thread-1", "thread-2"]
            return [{"id": "thread-1", "agent_user_id": "agent-1"}]

        def get_by_id(self, _thread_id: str):
            raise AssertionError("unexpected per-thread lookup")

        def close(self):
            pass

    owners = resource_common.thread_owners(
        ["thread-1", "thread-2"],
        thread_repo=_BatchOnlyThreadRepo(),
        user_repo=_FakeUserRepo([_FakeAgent("agent-1", "Toad", avatar="x")]),
    )

    assert owners == {
        "thread-1": {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": "/api/users/agent-1/avatar"},
        "thread-2": {"agent_user_id": None, "agent_name": "未绑定Agent", "avatar_url": None},
    }

@pytest.mark.parametrize(
    ("thread_repo", "user_repo", "message"),
    [
        (
            type(
                "_BrokenThreadRepo",
                (),
                {
                    "list_by_ids": lambda self, _thread_ids: (_ for _ in ()).throw(RuntimeError("thread repo offline")),
                    "close": lambda self: None,
                },
            )(),
            _FakeUserRepo([_FakeAgent("agent-1", "Toad", avatar="x")]),
            "thread repo offline",
        ),
        (
            _FakeThreadRepo({"thread-1": {"agent_user_id": "agent-1"}}),
            type(
                "_BrokenUserRepo",
                (),
                {
                    "list_all": lambda self: (_ for _ in ()).throw(RuntimeError("user repo offline")),
                    "close": lambda self: None,
                },
            )(),
            "user repo offline",
        ),
    ],
    ids=["thread-repo", "user-repo"],
)
def test_thread_owners_fail_loudly_on_repo_errors(thread_repo, user_repo, message) -> None:
    with pytest.raises(RuntimeError, match=message):
        resource_common.thread_owners(
            ["thread-1"],
            thread_repo=thread_repo,
            user_repo=user_repo,
        )


def test_metric_adds_error_only_when_present():
    assert resource_common.metric(1, 2, "%", "api", "live") == {
        "used": 1,
        "limit": 2,
        "unit": "%",
        "source": "api",
        "freshness": "live",
    }
    assert resource_common.metric(None, None, "GB", "unknown", "stale", "probe failed") == {
        "used": None,
        "limit": None,
        "unit": "GB",
        "source": "unknown",
        "freshness": "stale",
        "error": "probe failed",
    }
