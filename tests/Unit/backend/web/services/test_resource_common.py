from backend.web.services import resource_common


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

    def close(self):
        pass


class _FakeAgent:
    def __init__(self, user_id: str, name: str, avatar: str | None = None):
        self.id = user_id
        self.name = name
        self.avatar = avatar


class _FakeMemberRepo:
    def __init__(self, members):
        self._members = members

    def list_all(self):
        return list(self._members)

    def close(self):
        pass


def test_thread_owners_resolves_member_metadata_from_runtime_storage():
    owners = resource_common.thread_owners(
        ["thread-1", "thread-2"],
        thread_repo=_FakeThreadRepo({"thread-1": {"agent_user_id": "agent-1"}}),
        member_repo=_FakeMemberRepo([_FakeAgent("agent-1", "Toad")]),
    )

    assert owners == {
        "thread-1": {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": None},
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
