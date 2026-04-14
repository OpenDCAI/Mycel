from storage.contracts import SandboxRow


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


class _FakeSchema:
    def __init__(self, table_obj: _FakeTable) -> None:
        self.table_obj = table_obj

    def table(self, _name):
        return self.table_obj


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()
        self.schema_name = None
        self.table_name = None

    def schema(self, name):
        self.schema_name = name
        return _FakeSchema(self.table_obj)


def test_supabase_sandbox_repo_create_writes_container_shape() -> None:
    from storage.providers.supabase.sandbox_repo import SupabaseSandboxRepo

    client = _FakeClient()
    repo = SupabaseSandboxRepo(client)
    row = SandboxRow(
        id="sandbox-1",
        owner_user_id="owner-1",
        provider_name="local",
        provider_env_id="env-1",
        sandbox_template_id="tpl-1",
        desired_state="running",
        observed_state="running",
        status="ready",
        observed_at=123.0,
        last_error=None,
        config={"cwd": "/workspace"},
        created_at=100.0,
        updated_at=123.0,
    )

    repo.create(row)

    assert client.schema_name == "container"
    assert client.table_obj.insert_payload["id"] == "sandbox-1"
    assert client.table_obj.insert_payload["provider_name"] == "local"
    assert client.table_obj.insert_payload["config"] == {"cwd": "/workspace"}


def test_supabase_sandbox_repo_get_by_id_returns_row() -> None:
    from storage.providers.supabase.sandbox_repo import SupabaseSandboxRepo

    client = _FakeClient()
    client.table_obj.rows = [
        {
            "id": "sandbox-1",
            "owner_user_id": "owner-1",
            "provider_name": "local",
            "provider_env_id": "env-1",
            "sandbox_template_id": "tpl-1",
            "desired_state": "running",
            "observed_state": "running",
            "status": "ready",
            "observed_at": "2026-04-15T00:00:00+00:00",
            "last_error": None,
            "config": {"cwd": "/workspace"},
            "created_at": "2026-04-15T00:00:00+00:00",
            "updated_at": "2026-04-15T00:01:00+00:00",
        }
    ]
    repo = SupabaseSandboxRepo(client)

    row = repo.get_by_id("sandbox-1")

    assert row is not None
    assert row.id == "sandbox-1"
    assert row.provider_name == "local"
    assert row.config == {"cwd": "/workspace"}


def test_supabase_sandbox_repo_get_by_id_returns_none_when_missing() -> None:
    from storage.providers.supabase.sandbox_repo import SupabaseSandboxRepo

    client = _FakeClient()
    repo = SupabaseSandboxRepo(client)

    assert repo.get_by_id("missing") is None
