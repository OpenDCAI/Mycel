"""Explicit runtime schema routing for Supabase storage repos."""

from __future__ import annotations

import os
from collections.abc import Mapping

SUPPORTED_RUNTIME_SCHEMAS = frozenset({"public", "staging"})


def resolve_runtime_schema(schema: str | None = None) -> str:
    resolved = schema or os.getenv("LEON_DB_SCHEMA")
    if not resolved:
        raise RuntimeError("LEON_DB_SCHEMA is required for Supabase storage runtime.")
    if resolved not in SUPPORTED_RUNTIME_SCHEMAS:
        allowed = ", ".join(sorted(SUPPORTED_RUNTIME_SCHEMAS))
        raise RuntimeError(f"Unsupported LEON_DB_SCHEMA={resolved!r}. Supported runtime schemas: {allowed}.")
    return resolved


def route_for_schema(repo: str, mapping: Mapping[str, str], schema: str | None = None) -> str:
    resolved = resolve_runtime_schema(schema)
    if resolved not in mapping:
        allowed = ", ".join(sorted(mapping))
        raise RuntimeError(f"Supabase {repo} has no route for LEON_DB_SCHEMA={resolved!r}. Routed schemas: {allowed}.")
    return mapping[resolved]
