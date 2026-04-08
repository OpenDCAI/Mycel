from backend.web.services import resource_common


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

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


def test_thread_owners_resolves_member_metadata_from_runtime_storage():
    owners = resource_common.thread_owners(
        ["thread-1", "thread-2"],
        thread_repo=_FakeThreadRepo({"thread-1": {"agent_user_id": "agent-1"}}),
        user_repo=_FakeUserRepo([_FakeAgent("agent-1", "Toad", avatar="x")]),
    )

    assert owners == {
        "thread-1": {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": "/api/users/agent-1/avatar"},
        "thread-2": {"agent_user_id": None, "agent_name": "未绑定Agent", "avatar_url": None},
    }


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
