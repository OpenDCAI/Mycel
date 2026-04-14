#!/usr/bin/env bash
set -euo pipefail

required_env=(
  LEON_STORAGE_STRATEGY
  LEON_SUPABASE_CLIENT_FACTORY
  LEON_DB_SCHEMA
  SUPABASE_PUBLIC_URL
  SUPABASE_INTERNAL_URL
  SUPABASE_AUTH_URL
  SUPABASE_ANON_KEY
  LEON_SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_JWT_SECRET
  LEON_POSTGRES_URL
  MYCEL_BACKEND_BASE_URL
  MYCEL_SMOKE_IDENTIFIER
  MYCEL_SMOKE_PASSWORD
)

missing=()
for key in "${required_env[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    missing+=("$key")
  fi
done

if [[ -z "${OPENAI_API_KEY:-}" && -z "${ANTHROPIC_API_KEY:-}" ]]; then
  missing+=("OPENAI_API_KEY|ANTHROPIC_API_KEY")
fi

if (( ${#missing[@]} > 0 )); then
  printf 'Missing required environment variables:\n' >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi

python3 - <<'PY'
from __future__ import annotations

import json
import os
import sys
from urllib import error, parse, request


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


base_url = os.environ["MYCEL_BACKEND_BASE_URL"].rstrip("/")
identifier = os.environ["MYCEL_SMOKE_IDENTIFIER"]
password = os.environ["MYCEL_SMOKE_PASSWORD"]


def request_json(path: str, *, method: str, payload: dict[str, object] | None = None, token: str | None = None) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(f"{base_url}{path}", data=body, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        fail(f"{path} returned {exc.code}: {detail or '<empty body>'}")
    except Exception as exc:  # noqa: BLE001
        fail(f"{path} request failed: {exc}")

    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        fail(f"{path} returned non-JSON body: {exc}")
    if not isinstance(parsed, dict):
        fail(f"{path} returned non-object JSON")
    return parsed


def _is_string_or_nullish(value: object) -> bool:
    return value is None or isinstance(value, str)


def has_frontend_valid_launch_config(payload: dict[str, object]) -> bool:
    # @@@default-config-shape - keep smoke acceptance aligned with the frontend parser
    # so this gate cannot pass a payload that `getDefaultThreadConfig()` would reject.
    source = payload.get("source")
    if source not in {"last_successful", "last_confirmed", "derived"}:
        return False
    config = payload.get("config")
    if not isinstance(config, dict):
        return False
    create_mode = config.get("create_mode")
    provider_config = config.get("provider_config")
    sandbox_template = config.get("sandbox_template")
    if create_mode not in {"new", "existing"}:
        return False
    if not isinstance(provider_config, str) or not provider_config:
        return False
    if sandbox_template is not None and not isinstance(sandbox_template, dict):
        return False
    return (
        _is_string_or_nullish(config.get("existing_sandbox_id"))
        and _is_string_or_nullish(config.get("model"))
        and _is_string_or_nullish(config.get("workspace"))
    )


login = request_json(
    "/api/auth/login",
    method="POST",
    payload={"identifier": identifier, "password": password},
)
token = str(login.get("token") or "").strip()
if not token:
    fail("/api/auth/login returned no token")
print("login ok")

agents = request_json("/api/panel/agents", method="GET", token=token)
items = agents.get("items")
if not isinstance(items, list):
    fail("/api/panel/agents returned no items list")
if not items:
    fail("/api/panel/agents returned no owned agents")
first_agent = items[0]
if not isinstance(first_agent, dict):
    fail("/api/panel/agents first item is not an object")
agent_user_id = str(first_agent.get("id") or "").strip()
if not agent_user_id:
    fail("/api/panel/agents first item has no id")
print(f"panel agents ok: {agent_user_id}")

default_config = request_json(
    f"/api/threads/default-config?agent_user_id={parse.quote(agent_user_id, safe='')}",
    method="GET",
    token=token,
)
if not has_frontend_valid_launch_config(default_config):
    fail("/api/threads/default-config returned malformed launch config")
print("default-config ok")
print("dev validity smoke passed")
PY
