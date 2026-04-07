from storage.providers.supabase.thread_launch_pref_repo import SupabaseThreadLaunchPrefRepo


class _FakeTable:
    def __init__(self) -> None:
        self.eq_calls: list[tuple[str, object]] = []
        self.upsert_payload = None
        self.upsert_conflict = None
        self.rows = [
            {
                "owner_user_id": "owner-1",
                "agent_user_id": "agent-1",
                "last_confirmed_json": '{"provider_config":"local"}',
                "last_successful_json": '{"provider_config":"daytona_selfhost"}',
                "last_confirmed_at": 1.0,
                "last_successful_at": 2.0,
            }
        ]

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def upsert(self, payload, on_conflict=None):
        self.upsert_payload = payload
        self.upsert_conflict = on_conflict
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()

    def table(self, _name):
        return self.table_obj


def test_supabase_thread_launch_pref_repo_get_filters_on_agent_user_id() -> None:
    client = _FakeClient()
    repo = SupabaseThreadLaunchPrefRepo(client)

    result = repo.get("owner-1", "agent-1")

    assert result is not None
    assert result["agent_user_id"] == "agent-1"
    assert ("agent_user_id", "agent-1") in client.table_obj.eq_calls
    assert ("member_id", "agent-1") not in client.table_obj.eq_calls


def test_supabase_thread_launch_pref_repo_save_successful_upserts_on_agent_user_pair() -> None:
    client = _FakeClient()
    repo = SupabaseThreadLaunchPrefRepo(client)

    repo.save_successful("owner-1", "agent-1", {"provider_config": "local"})

    assert client.table_obj.upsert_payload is not None
    assert client.table_obj.upsert_payload["owner_user_id"] == "owner-1"
    assert client.table_obj.upsert_payload["agent_user_id"] == "agent-1"
    assert client.table_obj.upsert_conflict == "owner_user_id,agent_user_id"
