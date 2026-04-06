from types import SimpleNamespace

from backend.web.services import sandbox_service


class _FakeMonitorRepo:
    def __init__(self, rows):
        self._rows = rows

    def list_leases_with_threads(self):
        return list(self._rows)

    def close(self):
        pass


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

    def close(self):
        pass


class _FakeMemberRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, member_id: str):
        return self._rows.get(member_id)

    def close(self):
        pass


def test_list_user_leases_hides_subagent_threads_and_deduplicates_visible_agents(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_id": "thread-parent",
        },
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_id": "subagent-deadbeef",
        },
    ]
    thread_repo = _FakeThreadRepo(
        {
            "thread-parent": {"member_id": "member-1"},
            "subagent-deadbeef": {"member_id": "member-1"},
        }
    )
    member_repo = _FakeMemberRepo(
        {
            "member-1": SimpleNamespace(id="member-1", name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        member_repo=member_repo,
    )

    assert leases == [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe": {
                "id": "daytona:default",
                "name": "Daytona Default",
                "desc": "Default recipe for daytona",
                "provider_type": "daytona",
                "features": {"lark_cli": False},
                "configurable_features": {"lark_cli": True},
                "feature_options": [
                    {
                        "key": "lark_cli",
                        "name": "Lark CLI",
                        "description": "在 sandbox 初始化时懒安装并校验。",
                        "icon": "feishu",
                    }
                ],
                "builtin": True,
            },
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_ids": ["thread-parent"],
            "agents": [
                {
                    "member_id": "member-1",
                    "member_name": "Morel",
                    "avatar_url": "/api/members/member-1/avatar",
                }
            ],
            "recipe_name": "Daytona Default",
        }
    ]
