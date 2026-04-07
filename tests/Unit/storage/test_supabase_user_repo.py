from storage.contracts import UserRow, UserType
from storage.providers.supabase.user_repo import SupabaseUserRepo


class _FakeTable:
    def __init__(self) -> None:
        self.insert_payload = None
        self.update_payload = None
        self.eq_calls: list[tuple[str, object]] = []
        self.rows = [
            {
                "id": "user-1",
                "type": "agent",
                "display_name": "Toad",
                "owner_user_id": "owner-1",
                "agent_config_id": "cfg-1",
                "avatar": "toad.png",
                "email": "toad@example.com",
                "mycel_id": 10001,
                "created_at": 1.0,
                "updated_at": 2.0,
            }
        ]

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def update(self, payload):
        self.update_payload = payload
        return self

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def order(self, _column, desc=False):
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_name = None
        self.table_obj = _FakeTable()

    def table(self, name):
        self.table_name = name
        return self.table_obj


def test_supabase_user_repo_create_persists_agent_identity_fields() -> None:
    client = _FakeClient()
    repo = SupabaseUserRepo(client)

    repo.create(
        UserRow(
            id="user-1",
            type=UserType.AGENT,
            display_name="Toad",
            owner_user_id="owner-1",
            agent_config_id="cfg-1",
            avatar="toad.png",
            email="toad@example.com",
            mycel_id=10001,
            created_at=1.0,
            updated_at=2.0,
        )
    )

    assert client.table_name == "users"
    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["type"] == "agent"
    assert client.table_obj.insert_payload["owner_user_id"] == "owner-1"
    assert client.table_obj.insert_payload["agent_config_id"] == "cfg-1"


def test_supabase_user_repo_get_by_id_returns_user_row() -> None:
    client = _FakeClient()
    repo = SupabaseUserRepo(client)

    row = repo.get_by_id("user-1")

    assert row is not None
    assert row.id == "user-1"
    assert row.type is UserType.AGENT
    assert row.owner_user_id == "owner-1"
    assert ("id", "user-1") in client.table_obj.eq_calls


def test_supabase_user_repo_list_by_owner_user_id_filters_on_owner() -> None:
    client = _FakeClient()
    repo = SupabaseUserRepo(client)

    rows = repo.list_by_owner_user_id("owner-1")

    assert [row.id for row in rows] == ["user-1"]
    assert ("owner_user_id", "owner-1") in client.table_obj.eq_calls
