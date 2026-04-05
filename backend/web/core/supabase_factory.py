"""Runtime Supabase client factory for storage wiring."""

from __future__ import annotations

import os

from supabase import create_client


def create_supabase_client():
    """Build a supabase-py client using service role key (legacy repos)."""
    url = os.getenv("SUPABASE_PUBLIC_URL")
    key = os.getenv("LEON_SUPABASE_SERVICE_ROLE_KEY")
    if not url:
        raise RuntimeError("SUPABASE_PUBLIC_URL is required for Supabase storage runtime.")
    if not key:
        raise RuntimeError("LEON_SUPABASE_SERVICE_ROLE_KEY is required for Supabase storage runtime.")
    return create_client(url, key)


def create_messaging_supabase_client():
    """Build a supabase-py client for messaging repos using anon key.

    The anon key works for messaging tables which have no RLS policies
    in the current self-hosted setup.
    """
    url = os.getenv("SUPABASE_PUBLIC_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url:
        raise RuntimeError("SUPABASE_PUBLIC_URL is required for messaging.")
    if not key:
        raise RuntimeError("SUPABASE_ANON_KEY is required for messaging.")
    return create_client(url, key)
