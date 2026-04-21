"""Compatibility shell for neutral Supabase runtime factories.

@@@env-ref-kept - external env files still reference this exact path via
`LEON_SUPABASE_CLIENT_FACTORY=backend.web.core.supabase_factory:create_supabase_client`.
Do NOT delete this file until all ops/env files have been migrated.
The canonical implementation now lives at backend.identity.auth.supabase_runtime.
"""

from backend.identity.auth.supabase_runtime import create_client, create_supabase_auth_client, create_supabase_client

__all__ = ["create_client", "create_supabase_auth_client", "create_supabase_client"]
