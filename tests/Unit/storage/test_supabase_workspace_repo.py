from storage.contracts import WorkspaceRow


class _FakeTable:
    def __init__(self) -> None:
        self.insert_payload = None
        self.rows: list[dict] = []
        self.eq_calls: list[tuple[str, object]] = []

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def execute(self):
        rows = self.rows
        for key, value in self.eq_calls:
            rows = [row for row in rows if row.get(key) == value]
        return type("Resp", (), {"data": rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()

    def schema(self, _name):
        return self

    def table(self, _name):
        return self.table_obj


def test_supabase_workspace_repo_create_writes_container_shape() -> None:
    from storage.providers.supabase.workspace_repo import SupabaseWorkspaceRepo

    client = _FakeClient()
    repo = SupabaseWorkspaceRepo(client)

    repo.create(
        WorkspaceRow(
            id="workspace-1",
            sandbox_id="sandbox-1",
            owner_user_id="owner-1",
            workspace_path="/workspace/demo",
            name="demo",
            created_at=1.0,
            updated_at=2.0,
        )
    )

    assert client.table_obj.insert_payload["id"] == "workspace-1"
    assert client.table_obj.insert_payload["workspace_path"] == "/workspace/demo"


def test_supabase_workspace_repo_get_by_id_returns_none_when_missing() -> None:
    from storage.providers.supabase.workspace_repo import SupabaseWorkspaceRepo

    client = _FakeClient()
    repo = SupabaseWorkspaceRepo(client)

    assert repo.get_by_id("missing") is None
