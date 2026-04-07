import pytest

from storage.providers.supabase.lease_repo import SupabaseLeaseRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_lease_repo_adopt_instance_fails_loudly_if_bootstrap_reload_missing():
    repo = SupabaseLeaseRepo(client=FakeSupabaseClient(tables={"sandbox_leases": [], "sandbox_instances": []}))
    rows = iter([None, None])

    repo.create = lambda **_kwargs: {  # type: ignore[method-assign]
        "lease_id": "lease-1",
        "provider_name": "test-provider",
    }
    repo.get = lambda _lease_id: next(rows)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="failed to load lease after adopt_instance bootstrap"):
        repo.adopt_instance(
            lease_id="lease-1",
            provider_name="test-provider",
            instance_id="inst-123",
        )


class _FakeTable:
    def __init__(self) -> None:
        self.insert_payload = None
        self.eq_calls: list[tuple[str, object]] = []
        self.rows = [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
                "recipe_id": None,
                "workspace_key": None,
                "recipe_json": None,
                "current_instance_id": None,
                "instance_created_at": None,
                "desired_state": "running",
                "observed_state": "detached",
                "version": 0,
                "observed_at": "2026-04-07T00:00:00",
                "last_error": None,
                "needs_refresh": 0,
                "refresh_hint_at": None,
                "status": "active",
                "volume_id": None,
                "created_at": "2026-04-07T00:00:00",
                "updated_at": "2026-04-07T00:00:00",
            }
        ]

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.tables = {
            "sandbox_leases": _FakeTable(),
            "sandbox_instances": _FakeTable(),
        }

    def table(self, name):
        return self.tables[name]


def test_supabase_lease_repo_create_persists_integer_refresh_flag():
    client = _FakeClient()
    repo = SupabaseLeaseRepo(client)

    repo.create("lease-1", "local")

    refresh_flag = client.tables["sandbox_leases"].insert_payload["needs_refresh"]
    assert refresh_flag == 0
    assert type(refresh_flag) is int
