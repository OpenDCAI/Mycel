"""Shared auth bootstrap helpers for backend app lifecycles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.identity.auth.service import AuthService
from backend.identity.auth.supabase_runtime import create_supabase_auth_client


@dataclass(frozen=True)
class AuthRuntimeState:
    auth_service: object
    supabase_auth_client_factory: Callable[[], object]


def build_auth_runtime_state(storage_state, *, contact_repo) -> AuthRuntimeState:
    storage_container = storage_state.storage_container
    supabase_client = storage_state.supabase_client
    supabase_auth_client_factory = create_supabase_auth_client
    # @@@auth-runtime-borrowed-contact-repo - auth runtime seeds owner-agent
    # contacts, but chat-owned contact_repo must be borrowed explicitly by the
    # enclosing app bootstrap instead of being reopened inside this helper.
    auth_service = AuthService(
        users=storage_container.user_repo(),
        agent_configs=storage_container.agent_config_repo(),
        supabase_client=supabase_client,
        supabase_auth_client_factory=supabase_auth_client_factory,
        invite_codes=storage_container.invite_code_repo(),
        contact_repo=contact_repo,
        recipe_repo=storage_container.recipe_repo(),
    )
    return AuthRuntimeState(
        auth_service=auth_service,
        supabase_auth_client_factory=supabase_auth_client_factory,
    )


def attach_auth_runtime_state(app, *, storage_state, contact_repo) -> AuthRuntimeState:
    state = build_auth_runtime_state(storage_state, contact_repo=contact_repo)
    app.state.auth_service = state.auth_service
    app.state._supabase_auth_client_factory = state.supabase_auth_client_factory
    return state
