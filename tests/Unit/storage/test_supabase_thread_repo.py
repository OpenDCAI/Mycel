from storage.providers.supabase.thread_repo import SupabaseThreadRepo


class _FakeTable:
    def __init__(self) -> None:
        self.insert_payload = None
        self.update_payload = None
        self.eq_calls: list[tuple[str, object]] = []
        self.rows = [
            {
                "id": "thread-1",
                "member_id": "member-1",
                "sandbox_type": "local",
                "model": None,
                "cwd": None,
                "observation_provider": None,
                "is_main": 1,
                "branch_index": 0,
                "created_at": 1.0,
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

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()

    def table(self, _name):
        return self.table_obj


def test_supabase_thread_repo_create_writes_integer_main_flag():
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.create(
        thread_id="thread-1",
        member_id="member-1",
        sandbox_type="local",
        created_at=1.0,
        is_main=True,
        branch_index=0,
    )

    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["is_main"] == 1


def test_supabase_thread_repo_update_writes_integer_main_flag():
    client = _FakeClient()
    client.table_obj.rows[0]["branch_index"] = 1
    client.table_obj.rows[0]["is_main"] = 0
    repo = SupabaseThreadRepo(client)

    repo.update("thread-1", is_main=False)

    assert client.table_obj.update_payload is not None
    assert client.table_obj.update_payload["is_main"] == 0


def test_supabase_thread_repo_get_default_thread_reads_by_member_and_main_flag():
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    result = repo.get_default_thread("member-1")

    assert result is not None
    assert result["id"] == "thread-1"
    assert ("member_id", "member-1") in client.table_obj.eq_calls
    assert ("is_main", 1) in client.table_obj.eq_calls
