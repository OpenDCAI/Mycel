"""Supabase repository for sandbox lease persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "lease repo"
_SCHEMA = "container"
_TABLE = "sandboxes"
_SANDBOX_COLS = (
    "id,owner_user_id,provider_name,provider_env_id,sandbox_template_id,"
    "desired_state,observed_state,status,observed_at,last_error,config,created_at,updated_at"
)
_LEGACY_LEASE_ID = "legacy_lease_id"
_LEASE_COMPAT = "lease_compat"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sandbox_id_for_lease(lease_id: str) -> str:
    normalized = str(lease_id or "").strip()
    if not normalized:
        raise RuntimeError("lease_id is required")
    return f"sandbox-{uuid.uuid5(uuid.NAMESPACE_URL, f'mycel-lease-bridge:{normalized}').hex}"


def _config(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("config")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError(f"container sandbox config must be an object: {row.get('id')}")
    return dict(value)


def _bridge_state(row: dict[str, Any]) -> dict[str, Any]:
    value = _config(row).get(_LEASE_COMPAT)
    if value is None:
        raise RuntimeError(f"container sandbox missing config.{_LEASE_COMPAT}: {row.get('id')}")
    if not isinstance(value, dict):
        raise RuntimeError(f"container sandbox lease_compat must be an object: {row.get('id')}")
    return dict(value)


def _lease_id(row: dict[str, Any]) -> str:
    value = _config(row).get(_LEGACY_LEASE_ID)
    if isinstance(value, str):
        value = value.strip()
    if not value:
        raise RuntimeError(f"container sandbox missing config.{_LEGACY_LEASE_ID}: {row.get('id')}")
    return str(value)


def _has_lease_bridge_state(row: dict[str, Any]) -> bool:
    return _config(row).get(_LEASE_COMPAT) is not None


def _int_flag(value: Any) -> int:
    if value is None:
        return 0
    return 1 if bool(value) else 0


def _instance_from_lease(row: dict[str, Any]) -> dict[str, Any] | None:
    current_instance_id = row.get("current_instance_id")
    if not current_instance_id:
        return None
    return {
        "instance_id": current_instance_id,
        "lease_id": row.get("lease_id"),
        "provider_session_id": current_instance_id,
        "status": row.get("observed_state"),
        "created_at": row.get("instance_created_at"),
        "last_seen_at": row.get("observed_at"),
    }


def _lease_from_sandbox(row: dict[str, Any]) -> dict[str, Any]:
    bridge_state = _bridge_state(row)
    result = {
        "sandbox_id": row.get("id"),
        "lease_id": _lease_id(row),
        "provider_name": row.get("provider_name"),
        "recipe_id": bridge_state.get("recipe_id") or row.get("sandbox_template_id"),
        "workspace_key": bridge_state.get("workspace_key"),
        "recipe_json": bridge_state.get("recipe_json"),
        "current_instance_id": row.get("provider_env_id"),
        "instance_created_at": bridge_state.get("instance_created_at"),
        "desired_state": row.get("desired_state"),
        "observed_state": row.get("observed_state"),
        "instance_status": row.get("observed_state"),
        "version": int(bridge_state.get("version") or 0),
        "observed_at": row.get("observed_at"),
        "last_error": row.get("last_error"),
        "needs_refresh": _int_flag(bridge_state.get("needs_refresh")),
        "refresh_hint_at": bridge_state.get("refresh_hint_at"),
        "status": bridge_state.get("status") or "active",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    result["_instance"] = _instance_from_lease(result)
    return result


def _patched_config(row: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    config = _config(row)
    bridge_state = _bridge_state(row)
    bridge_state.update(updates)
    config[_LEASE_COMPAT] = bridge_state
    return config


class SupabaseLeaseRepo:
    """Container-backed LeaseRepo bridge for lower sandbox runtime contracts."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _sandboxes(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _TABLE, _REPO)

    def _require_lease(self, row: dict[str, Any] | None, *, lease_id: str, operation: str) -> dict[str, Any]:
        if row is None:
            raise RuntimeError(f"Supabase lease repo failed to load lease after {operation}: {lease_id}")
        return row

    def _sandbox_rows(self) -> list[dict[str, Any]]:
        rows = q.rows(self._sandboxes().select(_SANDBOX_COLS).execute(), _REPO, "list sandboxes")
        return [dict(row) for row in rows if _config(dict(row)).get(_LEGACY_LEASE_ID)]

    def _sandbox_by_lease_id(self, lease_id: str) -> dict[str, Any] | None:
        for row in self._sandbox_rows():
            if _lease_id(row) == lease_id:
                return row
        return None

    def get(self, lease_id: str) -> dict[str, Any] | None:
        row = self._sandbox_by_lease_id(lease_id)
        if row is None:
            return None
        return _lease_from_sandbox(row)

    def create(
        self,
        lease_id: str,
        provider_name: str,
        recipe_id: str | None = None,
        recipe_json: str | None = None,
        *,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        if not owner_user_id:
            raise RuntimeError("Supabase lease repo create requires owner_user_id for container.sandboxes")
        now = _utc_now_iso()
        self._sandboxes().insert(
            {
                "id": _sandbox_id_for_lease(lease_id),
                "owner_user_id": owner_user_id,
                "provider_name": provider_name,
                "provider_env_id": None,
                "sandbox_template_id": recipe_id,
                "desired_state": "running",
                "observed_state": "detached",
                "status": "ready",
                "observed_at": now,
                "last_error": None,
                "config": {
                    _LEGACY_LEASE_ID: lease_id,
                    _LEASE_COMPAT: {
                        "recipe_id": recipe_id,
                        "recipe_json": recipe_json,
                        "workspace_key": None,
                        "instance_created_at": None,
                        "version": 0,
                        "needs_refresh": 0,
                        "refresh_hint_at": None,
                        "status": "active",
                    },
                },
                "created_at": now,
                "updated_at": now,
            }
        ).execute()
        return self._require_lease(self.get(lease_id), lease_id=lease_id, operation="create")

    def find_by_instance(self, *, provider_name: str, instance_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(
                self._sandboxes().select(_SANDBOX_COLS).eq("provider_name", provider_name).eq("provider_env_id", instance_id),
                1,
                _REPO,
                "find_by_instance",
            ).execute(),
            _REPO,
            "find_by_instance",
        )
        return _lease_from_sandbox(dict(rows[0])) if rows else None

    def adopt_instance(
        self,
        *,
        lease_id: str,
        provider_name: str,
        instance_id: str,
        status: str = "unknown",
    ) -> dict[str, Any]:
        from sandbox.lifecycle import parse_lease_instance_state

        existing = self._require_lease(self.get(lease_id), lease_id=lease_id, operation="adopt_instance")
        if existing["provider_name"] != provider_name:
            raise RuntimeError(f"Lease provider mismatch during adopt: lease={existing['provider_name']}, requested={provider_name}")

        row = self._require_lease(self._sandbox_by_lease_id(lease_id), lease_id=lease_id, operation="adopt_instance sandbox")
        now = _utc_now_iso()
        normalized = parse_lease_instance_state(status).value
        desired = "paused" if normalized == "paused" else "running"
        self._sandboxes().update(
            {
                "provider_env_id": instance_id,
                "desired_state": desired,
                "observed_state": normalized,
                "observed_at": now,
                "last_error": None,
                "status": "active",
                "updated_at": now,
                "config": _patched_config(
                    row,
                    {
                        "instance_created_at": now,
                        "version": int(existing.get("version") or 0) + 1,
                        "needs_refresh": 1,
                        "refresh_hint_at": now,
                        "status": "active",
                    },
                ),
            }
        ).eq("id", row["id"]).execute()
        return self._require_lease(self.get(lease_id), lease_id=lease_id, operation="adopt_instance")

    def observe_status(
        self,
        *,
        lease_id: str,
        status: str,
        observed_at: Any = None,
    ) -> dict[str, Any]:
        from sandbox.lifecycle import parse_lease_instance_state

        existing = self._require_lease(self.get(lease_id), lease_id=lease_id, operation="observe_status")
        row = self._require_lease(self._sandbox_by_lease_id(lease_id), lease_id=lease_id, operation="observe_status sandbox")
        now = observed_at.isoformat() if isinstance(observed_at, datetime) else (observed_at or _utc_now_iso())
        normalized = parse_lease_instance_state(status).value
        lease_status = "expired" if normalized == "detached" else "active"
        self._sandboxes().update(
            {
                "provider_env_id": None if normalized == "detached" else existing.get("current_instance_id"),
                "observed_state": normalized,
                "observed_at": now,
                "last_error": None,
                "status": lease_status,
                "updated_at": _utc_now_iso(),
                "config": _patched_config(
                    row,
                    {
                        "instance_created_at": None if normalized == "detached" else existing.get("instance_created_at"),
                        "version": int(existing.get("version") or 0) + 1,
                        "needs_refresh": 0,
                        "refresh_hint_at": None,
                        "status": lease_status,
                    },
                ),
            }
        ).eq("id", row["id"]).execute()
        return self._require_lease(self.get(lease_id), lease_id=lease_id, operation="observe_status")

    def persist_metadata(
        self,
        *,
        lease_id: str,
        recipe_id: str | None,
        recipe_json: str | None,
        desired_state: str,
        observed_state: str,
        version: int,
        observed_at: Any,
        last_error: str | None,
        needs_refresh: bool,
        refresh_hint_at: Any = None,
        status: str,
    ) -> dict[str, Any]:
        row = self._require_lease(self._sandbox_by_lease_id(lease_id), lease_id=lease_id, operation="persist_metadata sandbox")
        observed_at_value = observed_at.isoformat() if isinstance(observed_at, datetime) else observed_at
        refresh_hint_value = refresh_hint_at.isoformat() if isinstance(refresh_hint_at, datetime) else refresh_hint_at
        self._sandboxes().update(
            {
                "sandbox_template_id": recipe_id,
                "desired_state": desired_state,
                "observed_state": observed_state,
                "observed_at": observed_at_value,
                "last_error": last_error,
                "status": status,
                "updated_at": _utc_now_iso(),
                "config": _patched_config(
                    row,
                    {
                        "recipe_id": recipe_id,
                        "recipe_json": recipe_json,
                        "version": version,
                        "needs_refresh": 1 if needs_refresh else 0,
                        "refresh_hint_at": refresh_hint_value,
                        "status": status,
                    },
                ),
            }
        ).eq("id", row["id"]).execute()
        return self._require_lease(self.get(lease_id), lease_id=lease_id, operation="persist_metadata")

    def mark_needs_refresh(self, lease_id: str, hint_at: Any = None) -> bool:
        from datetime import datetime as _dt

        row = self._sandbox_by_lease_id(lease_id)
        if row is None:
            return False
        hinted_at = (hint_at or _dt.now(UTC)).isoformat() if not isinstance(hint_at, str) else hint_at
        response = (
            self._sandboxes()
            .update(
                {
                    "updated_at": _utc_now_iso(),
                    "config": _patched_config(row, {"needs_refresh": 1, "refresh_hint_at": hinted_at}),
                }
            )
            .eq("id", row["id"])
            .execute()
        )
        return len(q.rows(response, _REPO, "mark_needs_refresh")) > 0

    def delete(self, lease_id: str) -> None:
        row = self._sandbox_by_lease_id(lease_id)
        if row is None:
            return
        self._sandboxes().delete().eq("id", row["id"]).execute()

    def list_all(self) -> list[dict[str, Any]]:
        return sorted(
            [_lease_from_sandbox(row) for row in self._sandbox_rows() if _has_lease_bridge_state(row)],
            key=lambda row: row.get("created_at") or "",
            reverse=True,
        )

    def list_by_provider(self, provider_name: str) -> list[dict[str, Any]]:
        return [row for row in self.list_all() if row.get("provider_name") == provider_name]
