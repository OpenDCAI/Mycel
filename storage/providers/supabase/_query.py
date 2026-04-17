"""Shared PostgREST query helpers for all Supabase repos."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

IN_FILTER_CHUNK_SIZE = 80


def validate_client(client: Any, repo: str) -> Any:
    """Validate and return a Supabase client, raising on None or missing table()."""
    if client is None:
        raise RuntimeError(f"Supabase {repo} requires a client. Pass supabase_client=... into StorageContainer.")
    if not hasattr(client, "table"):
        raise RuntimeError(f"Supabase {repo} requires a supabase-py style client with table(name).")
    return client


def _preserve_postgrest_session(client: Any, schema: str) -> Any | None:
    postgrest = getattr(client, "postgrest", None)
    if postgrest is None:
        return None
    session = getattr(postgrest, "session", None)
    client_class = getattr(postgrest, "__class__", None)
    base_url = getattr(postgrest, "base_url", None)
    headers = getattr(postgrest, "headers", None)
    if session is None or client_class is None or base_url is None or headers is None:
        return None

    # @@@preserve-schema-session - postgrest-py schema() reconstructs a fresh httpx client
    # and drops any injected trust_env=False session; keep the original transport when scoping.
    try:
        scoped = client_class(
            base_url=str(base_url),
            schema=schema,
            headers=dict(headers),
            http_client=session,
        )
        if hasattr(postgrest, "timeout"):
            scoped.timeout = postgrest.timeout
        if hasattr(postgrest, "verify"):
            scoped.verify = postgrest.verify
        if hasattr(postgrest, "proxy"):
            scoped.proxy = postgrest.proxy
        return scoped
    except TypeError:
        return None


def schema_table(client: Any, schema: str, table: str, repo: str) -> Any:
    """Return a schema-qualified table query root, failing loudly if unsupported."""
    scoped = _preserve_postgrest_session(client, schema)
    schema_method = getattr(client, "schema", None)
    if scoped is None and not callable(schema_method):
        raise RuntimeError(f"Supabase {repo} requires client.schema({schema!r}) support for {schema}.{table}.")
    if scoped is None:
        assert callable(schema_method)
        scoped = schema_method(schema)
    table_method = getattr(scoped, "table", None)
    if not callable(table_method):
        raise RuntimeError(f"Supabase {repo} schema({schema!r}) result must expose table(name).")
    return table_method(table)


def schema_rpc(client: Any, schema: str, function_name: str, params: dict[str, Any], repo: str) -> Any:
    """Return a schema-qualified RPC query, failing loudly if unsupported."""
    scoped = _preserve_postgrest_session(client, schema)
    schema_method = getattr(client, "schema", None)
    if scoped is None and not callable(schema_method):
        raise RuntimeError(f"Supabase {repo} requires client.schema({schema!r}) support for {schema}.{function_name}.")
    if scoped is None:
        assert callable(schema_method)
        scoped = schema_method(schema)
    rpc_method = getattr(scoped, "rpc", None)
    if not callable(rpc_method):
        raise RuntimeError(f"Supabase {repo} schema({schema!r}) result must expose rpc(name, params).")
    return rpc_method(function_name, params)


def rows(response: Any, repo: str, operation: str) -> list[dict[str, Any]]:
    """Extract and validate the `.data` list from a supabase-py response."""
    if isinstance(response, dict):
        payload = response.get("data")
    else:
        payload = getattr(response, "data", None)
    if payload is None:
        raise RuntimeError(f"Supabase {repo} expected supabase-py `.data` payload for {operation}.")
    if not isinstance(payload, list):
        raise RuntimeError(f"Supabase {repo} expected list payload for {operation}, got {type(payload).__name__}.")
    for row in payload:
        if not isinstance(row, dict):
            raise RuntimeError(f"Supabase {repo} expected dict row for {operation}, got {type(row).__name__}.")
    return payload


def order(query: Any, column: str, *, desc: bool, repo: str, operation: str) -> Any:
    if not hasattr(query, "order"):
        raise RuntimeError(f"Supabase {repo} expects query.order() for {operation}. Use supabase-py.")
    return query.order(column, desc=desc)


def limit(query: Any, value: int, repo: str, operation: str) -> Any:
    if not hasattr(query, "limit"):
        raise RuntimeError(f"Supabase {repo} expects query.limit() for {operation}. Use supabase-py.")
    return query.limit(value)


def in_(query: Any, column: str, values: list[str], repo: str, operation: str) -> Any:
    if not hasattr(query, "in_"):
        raise RuntimeError(f"Supabase {repo} expects query.in_() for {operation}. Use supabase-py.")
    return query.in_(column, values)


def value_chunks(values: list[str]) -> list[list[str]]:
    return [values[i : i + IN_FILTER_CHUNK_SIZE] for i in range(0, len(values), IN_FILTER_CHUNK_SIZE)]


def rows_in_chunks(
    query_factory: Callable[[], Any],
    column: str,
    values: list[str],
    repo: str,
    operation: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for chunk in value_chunks(values):
        response = in_(query_factory(), column, chunk, repo, operation).execute()
        result.extend(rows(response, repo, operation))
    return result


def execute_in_chunks(
    query_factory: Callable[[], Any],
    column: str,
    values: list[str],
    repo: str,
    operation: str,
) -> None:
    for chunk in value_chunks(values):
        in_(query_factory(), column, chunk, repo, operation).execute()


def gt(query: Any, column: str, value: Any, repo: str, operation: str) -> Any:
    if not hasattr(query, "gt"):
        raise RuntimeError(f"Supabase {repo} expects query.gt() for {operation}. Use supabase-py.")
    return query.gt(column, value)


def gte(query: Any, column: str, value: Any, repo: str, operation: str) -> Any:
    if not hasattr(query, "gte"):
        raise RuntimeError(f"Supabase {repo} expects query.gte() for {operation}. Use supabase-py.")
    return query.gte(column, value)
