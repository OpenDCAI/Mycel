from datetime import UTC, datetime

from config.agent_config_types import Skill
from storage.container import StorageContainer
from storage.providers.supabase.skill_repo import SupabaseSkillRepo


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table_name: str, tables: dict[str, list[dict]]) -> None:
        self.table_name = table_name
        self.tables = tables
        self.eq_calls: list[tuple[str, object]] = []
        self.upsert_payload: dict | None = None
        self._delete = False

    def select(self, _columns: str):
        return self

    def eq(self, column: str, value: object):
        self.eq_calls.append((column, value))
        return self

    def upsert(self, payload: dict, *, on_conflict: str = ""):
        self.upsert_payload = dict(payload)
        self.tables.setdefault(self.table_name, []).append(dict(payload))
        return self

    def delete(self):
        self._delete = True
        return self

    def execute(self):
        rows = self.tables.setdefault(self.table_name, [])
        matching = [row for row in rows if all(row.get(column) == value for column, value in self.eq_calls)]
        if self._delete:
            self.tables[self.table_name] = [row for row in rows if row not in matching]
        if self.upsert_payload is not None:
            return _FakeResponse([self.upsert_payload])
        return _FakeResponse([dict(row) for row in matching])


class _FakeClient:
    def __init__(
        self, tables: dict[str, list[dict]] | None = None, schema_name: str | None = None, root: "_FakeClient | None" = None
    ) -> None:
        self.root = root or self
        self.tables = self.root.tables if root else (tables if tables is not None else {})
        self.table_queries = self.root.table_queries if root else {}
        self.schema_name = schema_name

    def table(self, name: str):
        resolved = f"{self.schema_name}.{name}" if self.schema_name else name
        query = _FakeQuery(resolved, self.tables)
        self.root.table_queries.setdefault(resolved, []).append(query)
        return query

    def schema(self, name: str):
        return _FakeClient(schema_name=name, root=self.root)


def _row(skill_id: str = "skill-1") -> dict:
    return {
        "id": skill_id,
        "owner_user_id": "owner-1",
        "name": "github",
        "description": "GitHub guidance",
        "version": "1.0.0",
        "content": "---\nname: github\n---\n",
        "files_json": {"references/query.md": "Prefer precise queries."},
        "source_json": {"source_version": "1.0.0"},
        "created_at": "2026-04-24T00:00:00+00:00",
        "updated_at": "2026-04-24T00:00:01+00:00",
    }


def test_list_for_owner_reads_skills_from_library() -> None:
    client = _FakeClient({"agent.skills": [_row()]})
    repo = SupabaseSkillRepo(client)

    skills = repo.list_for_owner("owner-1")

    assert [skill.name for skill in skills] == ["github"]
    assert skills[0].files == {"references/query.md": "Prefer precise queries."}
    assert ("owner_user_id", "owner-1") in client.table_queries["agent.skills"][0].eq_calls


def test_get_by_id_filters_owner_and_skill_id() -> None:
    client = _FakeClient({"agent.skills": [_row()]})
    repo = SupabaseSkillRepo(client)

    skill = repo.get_by_id("owner-1", "skill-1")

    assert skill is not None
    assert skill.id == "skill-1"
    assert ("owner_user_id", "owner-1") in client.table_queries["agent.skills"][0].eq_calls
    assert ("id", "skill-1") in client.table_queries["agent.skills"][0].eq_calls


def test_upsert_writes_full_skill_package() -> None:
    client = _FakeClient()
    repo = SupabaseSkillRepo(client)
    timestamp = datetime(2026, 4, 24, tzinfo=UTC)

    repo.upsert(
        Skill(
            id="skill-1",
            owner_user_id="owner-1",
            name="github",
            content="---\nname: github\n---\n",
            files={"references/query.md": "Prefer precise queries."},
            source={"source_version": "1.0.0"},
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    payload = client.table_queries["agent.skills"][0].upsert_payload
    assert payload is not None
    assert payload["id"] == "skill-1"
    assert payload["owner_user_id"] == "owner-1"
    assert payload["files_json"] == {"references/query.md": "Prefer precise queries."}
    assert payload["source_json"] == {"source_version": "1.0.0"}
    assert "files" not in payload
    assert "source" not in payload


def test_delete_filters_owner_and_skill_id() -> None:
    tables = {"agent.skills": [_row()]}
    client = _FakeClient(tables)
    repo = SupabaseSkillRepo(client)

    repo.delete("owner-1", "skill-1")

    assert tables["agent.skills"] == []


def test_storage_container_builds_skill_repo() -> None:
    client = _FakeClient()
    container = StorageContainer(client)

    repo = container.skill_repo()

    assert isinstance(repo, SupabaseSkillRepo)
