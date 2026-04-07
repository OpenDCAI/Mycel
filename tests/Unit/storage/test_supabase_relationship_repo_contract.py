from storage.providers.supabase.messaging_repo import SupabaseRelationshipRepo


class _FakeTable:
    def __init__(self) -> None:
        self.eq_calls: list[tuple[str, object]] = []
        self.insert_payload = None
        self.update_payload = None
        self.deleted = False
        self.rows = [
            {
                "user_low": "agent-user-1",
                "user_high": "human-user-1",
                "kind": "hire_visit",
                "state": "pending",
                "initiator_user_id": "human-user-1",
                "created_at": "2026-04-07T00:00:00Z",
                "updated_at": "2026-04-07T00:00:00Z",
            }
        ]

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def limit(self, _n):
        return self

    def update(self, payload):
        self.update_payload = payload
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def delete(self):
        self.deleted = True
        return self

    def or_(self, _expr):
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()

    def table(self, _name):
        return self.table_obj


def test_supabase_relationship_repo_get_queries_user_pair_and_kind() -> None:
    client = _FakeClient()
    repo = SupabaseRelationshipRepo(client)

    row = repo.get("human-user-1", "agent-user-1")

    assert row is not None
    assert row["user_low"] == "agent-user-1"
    assert row["user_high"] == "human-user-1"
    assert row["id"] == "hire_visit:agent-user-1:human-user-1"
    assert ("user_low", "agent-user-1") in client.table_obj.eq_calls
    assert ("user_high", "human-user-1") in client.table_obj.eq_calls
    assert ("kind", "hire_visit") in client.table_obj.eq_calls
    assert ("principal_a", "agent-user-1") not in client.table_obj.eq_calls
    assert ("principal_b", "human-user-1") not in client.table_obj.eq_calls


def test_supabase_relationship_repo_upsert_writes_pair_initiator_and_kind() -> None:
    client = _FakeClient()
    client.table_obj.rows = []
    repo = SupabaseRelationshipRepo(client)

    row = repo.upsert("human-user-1", "agent-user-1", state="pending", initiator_user_id="human-user-1")

    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["user_low"] == "agent-user-1"
    assert client.table_obj.insert_payload["user_high"] == "human-user-1"
    assert client.table_obj.insert_payload["kind"] == "hire_visit"
    assert client.table_obj.insert_payload["initiator_user_id"] == "human-user-1"
    assert "principal_a" not in client.table_obj.insert_payload
    assert "principal_b" not in client.table_obj.insert_payload
    assert row["id"] == "hire_visit:agent-user-1:human-user-1"
