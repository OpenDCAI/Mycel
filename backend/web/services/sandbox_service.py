"""Sandbox management service."""

import os
import uuid
from datetime import datetime
from typing import Any

from backend.web.core.config import LOCAL_WORKSPACE_ROOT, SANDBOXES_DIR
from backend.web.utils.helpers import is_virtual_thread_id
from sandbox.config import SandboxConfig
from sandbox.db import DEFAULT_DB_PATH as SANDBOX_DB_PATH
from sandbox.manager import SandboxManager


def build_provider_from_config_name(name: str) -> Any | None:
    """Build one provider instance from sandbox config name."""
    from sandbox.local import LocalSessionProvider

    if name == "local":
        return LocalSessionProvider(default_cwd=str(LOCAL_WORKSPACE_ROOT))

    try:
        config = SandboxConfig.load(name)
    except Exception as e:
        print(f"[sandbox] Failed to load {name}: {e}")
        return None

    try:
        if config.provider == "agentbay":
            from sandbox.providers.agentbay import AgentBayProvider

            key = config.agentbay.api_key or os.getenv("AGENTBAY_API_KEY")
            if not key:
                return None
            return AgentBayProvider(
                api_key=key,
                region_id=config.agentbay.region_id,
                default_context_path=config.agentbay.context_path,
                image_id=config.agentbay.image_id,
                provider_name=name,
                supports_pause=config.agentbay.supports_pause,
                supports_resume=config.agentbay.supports_resume,
            )

        if config.provider == "docker":
            from sandbox.providers.docker import DockerProvider

            return DockerProvider(
                image=config.docker.image,
                mount_path=config.docker.mount_path,
                provider_name=name,
            )

        if config.provider == "e2b":
            from sandbox.providers.e2b import E2BProvider

            key = config.e2b.api_key or os.getenv("E2B_API_KEY")
            if not key:
                return None
            return E2BProvider(
                api_key=key,
                template=config.e2b.template,
                default_cwd=config.e2b.cwd,
                timeout=config.e2b.timeout,
                provider_name=name,
            )

        if config.provider == "daytona":
            from sandbox.providers.daytona import DaytonaProvider

            key = config.daytona.api_key or os.getenv("DAYTONA_API_KEY")
            if not key:
                return None
            return DaytonaProvider(
                api_key=key,
                api_url=config.daytona.api_url,
                target=config.daytona.target,
                default_cwd=config.daytona.cwd,
                provider_name=name,
            )
    except Exception as e:
        print(f"[sandbox] Failed to init provider {name}: {e}")
        return None

    print(f"[sandbox] Unsupported provider kind in {name}: {config.provider}")
    return None


def available_sandbox_types() -> list[dict[str, Any]]:
    """Scan ~/.leon/sandboxes/ for configured providers."""
    types = [{"name": "local", "available": True}]
    if not SANDBOXES_DIR.exists():
        return types
    for f in sorted(SANDBOXES_DIR.glob("*.json")):
        name = f.stem
        try:
            SandboxConfig.load(name)
            types.append({"name": name, "available": True})
        except Exception as e:
            types.append({"name": name, "available": False, "reason": str(e)})
    return types


def init_providers_and_managers() -> tuple[dict, dict]:
    """Load sandbox providers and managers from config files."""
    providers: dict[str, Any] = {}
    local_provider = build_provider_from_config_name("local")
    if local_provider is not None:
        providers["local"] = local_provider
    if not SANDBOXES_DIR.exists():
        managers = {name: SandboxManager(provider=p, db_path=SANDBOX_DB_PATH) for name, p in providers.items()}
        return providers, managers

    for config_file in SANDBOXES_DIR.glob("*.json"):
        name = config_file.stem
        provider = build_provider_from_config_name(name)
        if provider is not None:
            providers[name] = provider

    managers = {name: SandboxManager(provider=p, db_path=SANDBOX_DB_PATH) for name, p in providers.items()}
    return providers, managers


def load_all_sessions(managers: dict) -> list[dict]:
    """Load sessions from all managers in parallel."""
    sessions: list[dict] = []
    if not managers:
        return sessions
    for provider_name, manager in managers.items():
        rows = manager.list_sessions()
        for row in rows:
            sessions.append(
                {
                    "session_id": row["session_id"],
                    "thread_id": row["thread_id"],
                    "provider": row.get("provider", provider_name),
                    "status": row.get("status", "running"),
                    "created_at": row.get("created_at"),
                    "last_active": row.get("last_active"),
                    "lease_id": row.get("lease_id"),
                    "instance_id": row.get("instance_id"),
                    "chat_session_id": row.get("chat_session_id"),
                    "source": row.get("source", "unknown"),
                    "inspect_visible": row.get("inspect_visible", True),
                }
            )

    # @@@stable-session-order - Keep deterministic ordering across refreshes/providers.
    def _to_ts(value: Any) -> float:
        if not value or not isinstance(value, str):
            return 0.0
        try:
            return datetime.fromisoformat(value).timestamp()
        except Exception:
            return 0.0

    sessions.sort(
        key=lambda row: (
            -_to_ts(row.get("created_at")),
            -_to_ts(row.get("last_active")),
            str(row.get("provider") or ""),
            str(row.get("thread_id") or ""),
            str(row.get("session_id") or ""),
        )
    )
    return sessions


def find_session_and_manager(
    sessions: list[dict],
    managers: dict,
    session_id: str,
    provider_name: str | None = None,
) -> tuple[dict | None, Any | None]:
    """Find session by ID/prefix (+optional provider), return (session, manager)."""
    candidates: list[dict] = []
    for s in sessions:
        if provider_name and s.get("provider") != provider_name:
            continue
        sid = str(s.get("session_id") or "")
        if sid == session_id or sid.startswith(session_id):
            candidates.append(s)
    if not candidates:
        return None, None
    if len(candidates) == 1:
        chosen = candidates[0]
        return chosen, managers.get(chosen["provider"])
    exact = [s for s in candidates if str(s.get("session_id") or "") == session_id]
    if len(exact) == 1:
        chosen = exact[0]
        return chosen, managers.get(chosen["provider"])
    raise RuntimeError(f"Ambiguous session_id '{session_id}'. Specify provider query param.")


def mutate_sandbox_session(
    *,
    session_id: str,
    action: str,
    provider_hint: str | None = None,
) -> dict[str, Any]:
    """Perform pause/resume/destroy action on a sandbox session."""
    _, managers = init_providers_and_managers()
    sessions = load_all_sessions(managers)
    session, manager = find_session_and_manager(sessions, managers, session_id, provider_name=provider_hint)
    if not session:
        raise RuntimeError(f"Session not found: {session_id}")

    provider_name = str(session.get("provider") or "")
    if not manager:
        raise RuntimeError(f"Provider manager unavailable: {provider_name}")

    thread_id = str(session.get("thread_id") or "")
    lease_id = session.get("lease_id")
    target_session_id = str(session.get("session_id") or session_id)

    ok = False
    mode = "lease_enforced"

    if manager and thread_id and not is_virtual_thread_id(thread_id):
        mode = "manager_thread"
        if action == "pause":
            ok = manager.pause_session(thread_id)
        elif action == "resume":
            ok = manager.resume_session(thread_id)
        elif action == "destroy":
            ok = manager.destroy_session(thread_id)
        else:
            raise RuntimeError(f"Unknown action: {action}")
    else:
        lease = manager.lease_store.get(lease_id) if lease_id else None
        if not lease:
            adopt_lease_id = str(lease_id or f"lease-adopt-{uuid.uuid4().hex[:12]}")
            adopt_status = str(session.get("status") or "unknown")
            lease = manager.lease_store.adopt_instance(
                lease_id=adopt_lease_id,
                provider_name=provider_name,
                instance_id=target_session_id,
                status=adopt_status,
            )
            lease_id = lease.lease_id

        mode = "manager_lease"
        if action == "pause":
            ok = lease.pause_instance(manager.provider)
        elif action == "resume":
            ok = lease.resume_instance(manager.provider)
        elif action == "destroy":
            lease.destroy_instance(manager.provider)
            ok = True
        else:
            raise RuntimeError(f"Unknown action: {action}")

    if not ok:
        raise RuntimeError(f"Failed to {action} session {target_session_id}")

    return {
        "ok": True,
        "action": action,
        "session_id": target_session_id,
        "provider": provider_name,
        "thread_id": thread_id or None,
        "lease_id": lease_id,
        "mode": mode,
    }


def destroy_thread_resources_sync(thread_id: str, sandbox_type: str, agent_pool: dict) -> bool:
    """Destroy sandbox resources for a thread."""
    pool_key = f"{thread_id}:{sandbox_type}"
    pooled_agent = agent_pool.get(pool_key)
    if pooled_agent and hasattr(pooled_agent, "_sandbox"):
        manager = pooled_agent._sandbox.manager
    else:
        _, managers = init_providers_and_managers()
        manager = managers.get(sandbox_type)
    if not manager:
        raise RuntimeError(f"No sandbox manager found for provider {sandbox_type}")
    return manager.destroy_thread_resources(thread_id)
