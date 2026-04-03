"""Runtime Supabase client factory for storage wiring."""

from __future__ import annotations

import os

import httpx
from supabase import Client, ClientOptions, create_client


def create_supabase_client():
    """Build a supabase-py client from runtime environment.

    Uses SUPABASE_INTERNAL_URL when available (direct server-side access, e.g. same-host
    or SSH tunnel), falling back to SUPABASE_PUBLIC_URL.  trust_env=False ensures the
    httpx client never routes through any system/VPN proxy.
    """
    # Prefer internal URL (same-host direct connection) over public tunnel URL.
    url = os.getenv("SUPABASE_INTERNAL_URL") or os.getenv("SUPABASE_PUBLIC_URL")
    key = os.getenv("LEON_SUPABASE_SERVICE_ROLE_KEY")
    if not url:
        raise RuntimeError("SUPABASE_INTERNAL_URL or SUPABASE_PUBLIC_URL is required.")
    if not key:
        raise RuntimeError("LEON_SUPABASE_SERVICE_ROLE_KEY is required for Supabase storage runtime.")
    schema = os.getenv("LEON_DB_SCHEMA", "public")
    timeout = httpx.Timeout(30.0, connect=10.0)
    http_client = httpx.Client(timeout=timeout, trust_env=False)
    return create_client(url, key, options=ClientOptions(httpx_client=http_client, schema=schema))
