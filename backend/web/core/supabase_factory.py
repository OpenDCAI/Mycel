"""Compatibility shell for neutral Supabase runtime factories."""

from backend.supabase_runtime import create_client, create_supabase_auth_client, create_supabase_client

__all__ = ["create_client", "create_supabase_auth_client", "create_supabase_client"]
