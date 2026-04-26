from __future__ import annotations

from typing import Any

import backend.sandboxes.user_reads as user_sandbox_reads
from backend.sandboxes.inventory import available_sandbox_types as list_available_sandbox_types
from backend.sandboxes.resources import provider_contracts as resource_provider_contracts


def load_user_sandboxes(app: Any, owner_user_id: str) -> list[dict[str, Any]]:
    thread_repo = getattr(app.state, "thread_repo", None)
    user_repo = getattr(app.state, "user_repo", None)
    if thread_repo is None or user_repo is None:
        raise RuntimeError("thread_repo and user_repo are required")

    return list_user_sandboxes(
        owner_user_id,
        thread_repo=thread_repo,
        user_repo=user_repo,
    )


def list_user_sandboxes(owner_user_id: str, **kwargs: Any) -> list[dict[str, Any]]:
    return user_sandbox_reads.list_user_sandboxes(owner_user_id, **kwargs)


def available_sandbox_types() -> list[dict[str, Any]]:
    return list_available_sandbox_types()


def get_provider_display_contract(config_name: str) -> dict[str, Any]:
    return resource_provider_contracts.get_provider_display_contract(config_name)


def get_provider_capability_contract(config_name: str) -> tuple[dict[str, Any], str | None]:
    return resource_provider_contracts.get_provider_capability_contract(config_name)


def build_provider_availability_payload(
    *,
    available: bool,
    running_count: int,
    unavailable_reason: str | None,
) -> dict[str, Any]:
    return resource_provider_contracts.build_provider_availability_payload(
        available=available,
        running_count=running_count,
        unavailable_reason=unavailable_reason,
    )


def build_resource_row_payload(
    *,
    resource_identity: str,
    sandbox_id: str | None,
    thread_id: str,
    runtime_id: str | None,
    owner: dict[str, Any],
    status: str,
    started_at: str,
    metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    return resource_provider_contracts.build_resource_row_payload(
        resource_identity=resource_identity,
        sandbox_id=sandbox_id,
        thread_id=thread_id,
        runtime_id=runtime_id,
        owner=owner,
        status=status,
        started_at=started_at,
        metrics=metrics,
    )
