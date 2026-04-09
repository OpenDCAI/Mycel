from storage.providers.supabase.terminal_repo import SupabaseTerminalRepo


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, client, name: str) -> None:
        self.client = client
        self.name = name
        self.mode = "select"
        self.filters: list[tuple[str, object]] = []
        self.update_payload = None
        self.in_values: list[str] | None = None
        self.order_key: str | None = None
        self.order_desc = False
        self.limit_value: int | None = None

    def select(self, _cols):
        self.mode = "select"
        return self

    def delete(self):
        self.mode = "delete"
        return self

    def update(self, payload):
        self.mode = "update"
        self.update_payload = payload
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, _key, values):
        self.in_values = list(values)
        return self

    def order(self, key, *, desc=False):
        self.order_key = key
        self.order_desc = desc
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def execute(self):
        if self.name == "abstract_terminals":
            return _FakeResponse(self._execute_terminals())
        if self.name == "thread_terminal_pointers":
            return _FakeResponse(self._execute_pointers())
        return _FakeResponse([])

    def _match(self, row: dict) -> bool:
        return all(row.get(key) == value for key, value in self.filters)

    def _execute_terminals(self):
        if self.mode == "select":
            rows = [dict(row) for row in self.client.terminals if self._match(row)]
            if self.order_key is not None:
                rows.sort(key=lambda row: row[self.order_key], reverse=self.order_desc)
            if self.limit_value is not None:
                rows = rows[: self.limit_value]
            return rows
        if self.mode == "update":
            for row in self.client.terminals:
                if self._match(row):
                    row.update(self.update_payload or {})
            return []
        if self.mode == "delete":
            terminal_id = next((value for key, value in self.filters if key == "terminal_id"), None)
            if terminal_id is not None:
                for pointer in self.client.pointers:
                    if pointer["active_terminal_id"] == terminal_id or pointer["default_terminal_id"] == terminal_id:
                        raise RuntimeError("pointer still references terminal")
            self.client.terminals = [row for row in self.client.terminals if not self._match(row)]
            return []
        raise AssertionError(f"unexpected terminal mode {self.mode}")

    def _execute_pointers(self):
        if self.mode == "select":
            return [dict(row) for row in self.client.pointers if self._match(row)]
        if self.mode == "delete":
            self.client.pointers = [row for row in self.client.pointers if not self._match(row)]
            return []
        if self.mode == "update":
            for row in self.client.pointers:
                if self._match(row):
                    row.update(self.update_payload or {})
            return []
        raise AssertionError(f"unexpected pointer mode {self.mode}")


class _FakeClient:
    def __init__(self, *, terminals: list[dict], pointers: list[dict]) -> None:
        self.terminals = [dict(row) for row in terminals]
        self.pointers = [dict(row) for row in pointers]

    def table(self, name: str):
        return _FakeTable(self, name)


def test_supabase_terminal_repo_delete_removes_pointer_before_deleting_last_terminal() -> None:
    client = _FakeClient(
        terminals=[
            {
                "terminal_id": "term-1",
                "thread_id": "thread-1",
                "lease_id": "lease-1",
                "cwd": "/workspace",
                "env_delta_json": "{}",
                "state_version": 0,
                "created_at": 1,
                "updated_at": 1,
            }
        ],
        pointers=[
            {
                "thread_id": "thread-1",
                "active_terminal_id": "term-1",
                "default_terminal_id": "term-1",
            }
        ],
    )
    repo = SupabaseTerminalRepo(client)

    repo.delete("term-1")

    assert client.terminals == []
    assert client.pointers == []


def test_supabase_terminal_repo_delete_updates_pointer_before_deleting_active_terminal() -> None:
    client = _FakeClient(
        terminals=[
            {
                "terminal_id": "term-new",
                "thread_id": "thread-1",
                "lease_id": "lease-1",
                "cwd": "/workspace",
                "env_delta_json": "{}",
                "state_version": 0,
                "created_at": 2,
                "updated_at": 2,
            },
            {
                "terminal_id": "term-old",
                "thread_id": "thread-1",
                "lease_id": "lease-1",
                "cwd": "/workspace",
                "env_delta_json": "{}",
                "state_version": 0,
                "created_at": 1,
                "updated_at": 1,
            },
        ],
        pointers=[
            {
                "thread_id": "thread-1",
                "active_terminal_id": "term-new",
                "default_terminal_id": "term-new",
            }
        ],
    )
    repo = SupabaseTerminalRepo(client)

    repo.delete("term-new")

    assert [row["terminal_id"] for row in client.terminals] == ["term-old"]
    assert client.pointers == [
        {
            "thread_id": "thread-1",
            "active_terminal_id": "term-old",
            "default_terminal_id": "term-old",
            "updated_at": client.pointers[0]["updated_at"],
        }
    ]


def test_supabase_terminal_repo_persists_terminal_state() -> None:
    client = _FakeClient(
        terminals=[
            {
                "terminal_id": "term-1",
                "thread_id": "thread-1",
                "lease_id": "lease-1",
                "cwd": "/workspace",
                "env_delta_json": "{}",
                "state_version": 0,
                "created_at": 1,
                "updated_at": 1,
            }
        ],
        pointers=[],
    )
    repo = SupabaseTerminalRepo(client)

    repo.persist_state(
        terminal_id="term-1",
        cwd="/workspace/next",
        env_delta_json='{"PWD":"/workspace/next"}',
        state_version=1,
    )

    row = client.terminals[0]
    assert row["cwd"] == "/workspace/next"
    assert row["env_delta_json"] == '{"PWD":"/workspace/next"}'
    assert row["state_version"] == 1
    assert row["updated_at"] != 1
