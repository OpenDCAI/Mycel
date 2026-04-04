"""Runtime Supabase client factories for storage and auth wiring."""

from __future__ import annotations

import os

import httpx
from supabase import ClientOptions, create_client


def _resolve_supabase_url() -> str:
    url = os.getenv("SUPABASE_INTERNAL_URL") or os.getenv("SUPABASE_PUBLIC_URL")
    if not url:
        raise RuntimeError("SUPABASE_INTERNAL_URL or SUPABASE_PUBLIC_URL is required.")
    return url


def create_supabase_client():
    """Build a supabase-py client from runtime environment.

    Uses SUPABASE_INTERNAL_URL when available (direct server-side access, e.g. same-host
    or SSH tunnel), falling back to SUPABASE_PUBLIC_URL.  trust_env=False ensures the
    httpx client never routes through any system/VPN proxy.
    """
    # Prefer internal URL (same-host direct connection) over public tunnel URL.
    url = _resolve_supabase_url()
    key = os.getenv("LEON_SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("LEON_SUPABASE_SERVICE_ROLE_KEY is required for Supabase storage runtime.")
    schema = os.getenv("LEON_DB_SCHEMA", "public")
    timeout = httpx.Timeout(30.0, connect=10.0)
    http_client = httpx.Client(timeout=timeout, trust_env=False)
    return create_client(url, key, options=ClientOptions(httpx_client=http_client, schema=schema))


def create_supabase_auth_client():
    """Build a supabase-py auth client for end-user auth flows.

    Uses the anon key rather than service-role credentials so auth endpoints
    behave like real caller traffic instead of admin/server traffic.
    """
    url = _resolve_supabase_url()
    key = os.getenv("SUPABASE_ANON_KEY")
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY is required for Supabase auth runtime.")
    timeout = httpx.Timeout(30.0, connect=10.0)
    http_client = httpx.Client(timeout=timeout, trust_env=False)
    return create_client(url, key, options=ClientOptions(httpx_client=http_client))
