"""In-memory fake Supabase client for unit tests.

Supports: select, insert, upsert, update, delete, eq, neq, in_, gt, gte, order, limit.
"""

from __future__ import annotations


class FakeSupabaseResponse:
    def __init__(self, data: list[dict]):
        self.data = data


class FakeSupabaseQuery:
    def __init__(self, table_name: str, tables: dict[str, list[dict]]):
        self._table_name = table_name
        self._tables = tables
        self._filters: list[tuple[str, str, object]] = []  # (column, op, value)
        self._in_filter: tuple[str, list[object]] | None = None
        self._order_by: tuple[str, bool] | None = None
        self._limit_value: int | None = None
        self._insert_payload: dict | list[dict] | None = None
        self._upsert_payload: dict | None = None
        self._upsert_conflict: str | None = None
        self._update_payload: dict | None = None
        self._delete_requested = False
        self._auto_seq = False

    def select(self, _columns: str):
        return self

    def insert(self, payload: dict | list[dict]):
        self._insert_payload = payload if isinstance(payload, list) else dict(payload)
        return self

    def upsert(self, payload: dict, *, on_conflict: str = ""):
        self._upsert_payload = dict(payload)
        self._upsert_conflict = on_conflict
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def delete(self):
        self._delete_requested = True
        return self

    def eq(self, column: str, value: object):
        self._filters.append((column, "eq", value))
        return self

    def neq(self, column: str, value: object):
        self._filters.append((column, "neq", value))
        return self

    def in_(self, column: str, values: list[object]):
        self._in_filter = (column, list(values))
        return self

    def gt(self, column: str, value: object):
        self._filters.append((column, "gt", value))
        return self

    def gte(self, column: str, value: object):
        self._filters.append((column, "gte", value))
        return self

    def order(self, column: str, desc: bool = False):
        self._order_by = (column, desc)
        return self

    def limit(self, value: int):
        self._limit_value = value
        return self

    def _match(self, row: dict) -> bool:
        for column, op, value in self._filters:
            cell = row.get(column)
            if op == "eq" and cell != value:
                return False
            if op == "neq" and cell == value:
                return False
            if op == "gt" and not (cell is not None and cell > value):
                return False
            if op == "gte" and not (cell is not None and cell >= value):
                return False
        if self._in_filter is not None:
            column, values = self._in_filter
            if row.get(column) not in values:
                return False
        return True

    def execute(self) -> FakeSupabaseResponse:
        table = self._tables.setdefault(self._table_name, [])

        # INSERT
        if self._insert_payload is not None:
            rows_to_insert = self._insert_payload if isinstance(self._insert_payload, list) else [self._insert_payload]
            inserted = []
            for payload in rows_to_insert:
                row = dict(payload)
                if self._auto_seq:
                    next_seq = 1 + max((int(r.get("seq", 0)) for r in table), default=0)
                    row["seq"] = next_seq
                table.append(row)
                inserted.append(dict(row))
            return FakeSupabaseResponse(inserted)

        # UPSERT
        if self._upsert_payload is not None:
            conflict_col = self._upsert_conflict or "id"
            conflict_val = self._upsert_payload.get(conflict_col)
            existing = [r for r in table if r.get(conflict_col) == conflict_val]
            if existing:
                existing[0].update(self._upsert_payload)
                return FakeSupabaseResponse([dict(existing[0])])
            row = dict(self._upsert_payload)
            table.append(row)
            return FakeSupabaseResponse([dict(row)])

        # Filter
        matching = [r for r in table if self._match(r)]

        # ORDER
        if self._order_by is not None:
            column, desc = self._order_by
            matching = sorted(matching, key=lambda r: r.get(column), reverse=desc)

        # LIMIT
        if self._limit_value is not None:
            matching = matching[:self._limit_value]

        # UPDATE
        if self._update_payload is not None:
            updated = []
            for row in table:
                if self._match(row):
                    row.update(self._update_payload)
                    updated.append(dict(row))
            return FakeSupabaseResponse(updated)

        # DELETE
        if self._delete_requested:
            self._tables[self._table_name] = [r for r in table if not self._match(r)]
            return FakeSupabaseResponse([dict(r) for r in matching])

        # SELECT
        return FakeSupabaseResponse([dict(r) for r in matching])


class FakeSupabaseClient:
    """In-memory Supabase client for tests.

    Args:
        tables: shared mutable dict of table_name -> list[dict].
        auto_seq_tables: set of table names that auto-generate a `seq` column on insert.
    """

    def __init__(
        self,
        tables: dict[str, list[dict]] | None = None,
        auto_seq_tables: set[str] | None = None,
    ):
        self._tables = tables if tables is not None else {}
        self._auto_seq_tables = auto_seq_tables or set()

    def table(self, table_name: str) -> FakeSupabaseQuery:
        query = FakeSupabaseQuery(table_name, self._tables)
        if table_name in self._auto_seq_tables:
            query._auto_seq = True
        return query
