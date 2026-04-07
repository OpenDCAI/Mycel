"""Runtime Supabase client factories for storage and auth wiring."""

from __future__ import annotations

import os

import httpx
from supabase import ClientOptions, create_client
from supabase_auth._sync.gotrue_client import SyncGoTrueClient


def _resolve_supabase_url() -> str:
    # Prefer SUPABASE_URL (new standard). Fall back to legacy split vars for
    # environments not yet migrated (e.g. Coolify production — see Step 7).
    url = os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_INTERNAL_URL") or os.getenv("SUPABASE_PUBLIC_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is required.")
    return url


def _resolve_supabase_auth_url() -> str:
    url = os.getenv("SUPABASE_AUTH_URL") or _resolve_supabase_url()
    return url


def create_supabase_client():
    """Build a service-role supabase-py client from runtime environment.

    Reads SUPABASE_URL (standard). Legacy fallback: SUPABASE_INTERNAL_URL, then
    SUPABASE_PUBLIC_URL (kept for environments not yet migrated to SUPABASE_URL).
    trust_env=False ensures httpx never routes through system/VPN proxy.
    """
    # Prefer internal URL (same-host direct connection) over public tunnel URL.
    url = _resolve_supabase_url()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for Supabase storage runtime.")
    timeout = httpx.Timeout(30.0, connect=10.0)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60.0)
    http_client = httpx.Client(timeout=timeout, trust_env=False, limits=limits)
    return create_client(url, key, options=ClientOptions(httpx_client=http_client))


def create_supabase_auth_client():
    """Build a supabase-py auth client for end-user auth flows.

    Uses the anon key rather than service-role credentials so auth endpoints
    behave like real caller traffic instead of admin/server traffic.
    """
    url = _resolve_supabase_auth_url()
    key = os.getenv("SUPABASE_ANON_KEY")
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY is required for Supabase auth runtime.")
    timeout = httpx.Timeout(30.0, connect=10.0)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5, keepalive_expiry=60.0)
    http_client = httpx.Client(timeout=timeout, trust_env=False, limits=limits)
    auth_url = os.getenv("SUPABASE_AUTH_URL")
    if auth_url:
        # @@@direct-gotrue - local auth may bypass Kong and hit GoTrue directly at /token.
        return SyncGoTrueClient(url=auth_url, headers={"apikey": key}, http_client=http_client)
    return create_client(url, key, options=ClientOptions(httpx_client=http_client))


