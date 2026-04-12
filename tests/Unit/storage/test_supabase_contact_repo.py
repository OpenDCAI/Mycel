from storage.providers.supabase.contact_repo import SupabaseContactRepo


class _FakeTable:
    def __init__(self) -> None:
        self.mode = "select"
        self.or_filter: str | None = None

    def delete(self):
        self.mode = "delete"
        return self

    def or_(self, value: str):
        self.or_filter = value
        return self

    def execute(self):
        return type("Resp", (), {"data": None})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()

    def table(self, _name: str):
        return self.table_obj


def test_supabase_contact_repo_delete_for_user_clears_source_and_target_edges() -> None:
    client = _FakeClient()
    repo = SupabaseContactRepo(client)

    repo.delete_for_user("agent-1")

    assert client.table_obj.mode == "delete"
    assert client.table_obj.or_filter == "source_user_id.eq.agent-1,target_user_id.eq.agent-1"
