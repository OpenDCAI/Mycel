"""User account resource limits."""

from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service
from sandbox.recipes import humanize_recipe_provider

SANDBOX_PROVIDER_ORDER = ("local", "daytona_selfhost", "daytona", "agentbay", "e2b", "docker")
DEFAULT_SANDBOX_LIMITS = {
    "local": 999,
    "daytona_selfhost": 2,
}
DEFAULT_WEEKLY_TOKEN_LIMIT = 100_000_000
SANDBOX_LABELS = {
    "daytona_selfhost": "Self-host Daytona",
}


class AccountResourceLimitExceededError(RuntimeError):
    def __init__(self, resource: dict[str, Any]) -> None:
        self.resource = resource
        super().__init__(f"{resource['label']} sandbox quota exceeded")


def _settings_repo(app: Any) -> Any:
    repo = getattr(app.state, "user_settings_repo", None)
    if repo is None:
        raise RuntimeError("user_settings_repo is required for account resource limits")
    return repo


def _normalized_user_sandbox_limits(raw_limits: dict[str, Any] | None) -> dict[str, int]:
    if raw_limits is None:
        return {}
    if not isinstance(raw_limits, dict):
        raise RuntimeError("account_resource_limits must be an object")
    sandbox_limits = raw_limits.get("sandbox")
    if sandbox_limits is None:
        return {}
    if not isinstance(sandbox_limits, dict):
        raise RuntimeError("account_resource_limits.sandbox must be an object")
    normalized: dict[str, int] = {}
    for provider_name, limit in sandbox_limits.items():
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise RuntimeError("account_resource_limits.sandbox provider names must be non-empty strings")
        if not isinstance(limit, int) or limit < 0:
            raise RuntimeError(f"account_resource_limits.sandbox.{provider_name} must be a non-negative integer")
        normalized[provider_name] = limit
    return normalized


def _weekly_token_limit(raw_limits: dict[str, Any] | None) -> int:
    if raw_limits is None:
        return DEFAULT_WEEKLY_TOKEN_LIMIT
    if not isinstance(raw_limits, dict):
        raise RuntimeError("account_resource_limits must be an object")
    token_limits = raw_limits.get("token")
    if token_limits is None:
        return DEFAULT_WEEKLY_TOKEN_LIMIT
    if not isinstance(token_limits, dict):
        raise RuntimeError("account_resource_limits.token must be an object")
    weekly = token_limits.get("weekly", DEFAULT_WEEKLY_TOKEN_LIMIT)
    if not isinstance(weekly, int) or weekly < 0:
        raise RuntimeError("account_resource_limits.token.weekly must be a non-negative integer")
    return weekly


def _sandbox_limits(app: Any, user_id: str) -> dict[str, int]:
    repo = _settings_repo(app)
    return {**DEFAULT_SANDBOX_LIMITS, **_normalized_user_sandbox_limits(repo.get_account_resource_limits(user_id))}


def list_account_resource_limits(app: Any, user_id: str) -> dict[str, list[dict[str, Any]]]:
    thread_repo = getattr(app.state, "thread_repo", None)
    if thread_repo is None:
        raise RuntimeError("thread_repo is required for account resource limits")

    count_kwargs = {"thread_repo": thread_repo}
    supabase_client = getattr(app.state, "_supabase_client", None)
    if supabase_client is not None:
        count_kwargs["supabase_client"] = supabase_client
    used_by_provider = sandbox_service.count_user_visible_leases_by_provider(user_id, **count_kwargs)
    raw_limits = _settings_repo(app).get_account_resource_limits(user_id)
    limits = {**DEFAULT_SANDBOX_LIMITS, **_normalized_user_sandbox_limits(raw_limits)}
    providers = sorted(
        set(SANDBOX_PROVIDER_ORDER) | set(limits) | set(used_by_provider),
        key=lambda name: (SANDBOX_PROVIDER_ORDER.index(name) if name in SANDBOX_PROVIDER_ORDER else len(SANDBOX_PROVIDER_ORDER), name),
    )

    items = []
    for provider_name in providers:
        limit = limits.get(provider_name, 0)
        used = used_by_provider.get(provider_name, 0)
        remaining = max(limit - used, 0)
        items.append(
            {
                "resource": "sandbox",
                "provider_name": provider_name,
                "label": SANDBOX_LABELS.get(provider_name, humanize_recipe_provider(provider_name)),
                "limit": limit,
                "used": used,
                "remaining": remaining,
                "can_create": remaining > 0,
            }
        )
    weekly_token_limit = _weekly_token_limit(raw_limits)
    items.append(
        {
            "resource": "token",
            "provider_name": "platform_tokens",
            "label": "平台 Token",
            "limit": weekly_token_limit,
            "used": 0,
            "remaining": weekly_token_limit,
            "can_create": weekly_token_limit > 0,
            "period": "weekly",
            "unit": "tokens",
        }
    )
    return {"items": items}


def assert_can_create_sandbox(app: Any, user_id: str, provider_name: str) -> None:
    resources = list_account_resource_limits(app, user_id)["items"]
    for item in resources:
        if item["resource"] == "sandbox" and item["provider_name"] == provider_name:
            if not item["can_create"]:
                raise AccountResourceLimitExceededError(item)
            return
    raise AccountResourceLimitExceededError(
        {
            "resource": "sandbox",
            "provider_name": provider_name,
            "label": humanize_recipe_provider(provider_name),
            "limit": 0,
            "used": 0,
            "remaining": 0,
            "can_create": False,
        }
    )
