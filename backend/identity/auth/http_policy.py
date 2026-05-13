from __future__ import annotations

import os

import httpx


def supabase_trust_env() -> bool:
    raw = str(os.getenv("LEON_SUPABASE_HTTP_TRUST_ENV") or "").strip().lower()
    if not raw:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError("LEON_SUPABASE_HTTP_TRUST_ENV must be one of: 1, true, yes, on, 0, false, no, off")


def supabase_http_client(*, timeout: httpx.Timeout) -> httpx.Client:
    return httpx.Client(timeout=timeout, trust_env=supabase_trust_env())
