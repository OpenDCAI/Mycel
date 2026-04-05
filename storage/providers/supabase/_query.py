"""Shared PostgREST query helpers for all Supabase repos."""

from __future__ import annotations

from typing import Any


def validate_client(client: Any, repo: str) -> Any:
    """Validate and return a Supabase client, raising on None or missing table()."""
    if client is None:
        raise RuntimeError(
            f"Supabase {repo} requires a client. "
            "Pass supabase_client=... into StorageContainer(strategy='supabase')."
        )
    if not hasattr(client, "table"):
        raise RuntimeError(
            f"Supabase {repo} requires a client with table(name). "
            "Use supabase-py client or a compatible adapter."
        )
    return client


def rows(response: Any, repo: str, operation: str) -> list[dict[str, Any]]:
    """Extract and validate the `.data` list from a supabase-py response."""
    if isinstance(response, dict):
        payload = response.get("data")
    else:
        payload = getattr(response, "data", None)
    if payload is None:
        raise RuntimeError(
            f"Supabase {repo} expected `.data` payload for {operation}. "
            "Check Supabase client compatibility."
        )
    if not isinstance(payload, list):
        raise RuntimeError(
            f"Supabase {repo} expected list payload for {operation}, got {type(payload).__name__}."
        )
    for row in payload:
        if not isinstance(row, dict):
            raise RuntimeError(
                f"Supabase {repo} expected dict row for {operation}, got {type(row).__name__}."
            )
    return payload


def order(query: Any, column: str, *, desc: bool, repo: str, operation: str) -> Any:
    if not hasattr(query, "order"):
        raise RuntimeError(
            f"Supabase {repo} expects query.order() for {operation}. Use supabase-py."
        )
    return query.order(column, desc=desc)


def limit(query: Any, value: int, repo: str, operation: str) -> Any:
    if not hasattr(query, "limit"):
        raise RuntimeError(
            f"Supabase {repo} expects query.limit() for {operation}. Use supabase-py."
        )
    return query.limit(value)


def in_(query: Any, column: str, values: list[str], repo: str, operation: str) -> Any:
    if not hasattr(query, "in_"):
        raise RuntimeError(
            f"Supabase {repo} expects query.in_() for {operation}. Use supabase-py."
        )
    return query.in_(column, values)


def gt(query: Any, column: str, value: Any, repo: str, operation: str) -> Any:
    if not hasattr(query, "gt"):
        raise RuntimeError(
            f"Supabase {repo} expects query.gt() for {operation}. Use supabase-py."
        )
    return query.gt(column, value)


def gte(query: Any, column: str, value: Any, repo: str, operation: str) -> Any:
    if not hasattr(query, "gte"):
        raise RuntimeError(
            f"Supabase {repo} expects query.gte() for {operation}. Use supabase-py."
        )
    return query.gte(column, value)
