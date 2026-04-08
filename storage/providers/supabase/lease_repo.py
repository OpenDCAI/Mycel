"""Supabase repository for sandbox lease persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "lease repo"
_LEASES_TABLE = "sandbox_leases"
_INSTANCES_TABLE = "sandbox_instances"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SupabaseLeaseRepo:
    """Sandbox lease CRUD backed by Supabase.

    Returns raw dicts — domain object construction is the consumer's job.
    """

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _require_lease(self, row: dict[str, Any] | None, *, lease_id: str, operation: str) -> dict[str, Any]:
        if row is None:
            raise RuntimeError(f"Supabase lease repo failed to load lease after {operation}: {lease_id}")
        return row

    def _leases(self) -> Any:
        return self._client.table(_LEASES_TABLE)

    def _instances(self) -> Any:
        return self._client.table(_INSTANCES_TABLE)

    def get(self, lease_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._leases()
            .select(
                "lease_id,provider_name,recipe_id,workspace_key,recipe_json,"
                "current_instance_id,instance_created_at,desired_state,observed_state,version,"
                "observed_at,last_error,needs_refresh,refresh_hint_at,status,volume_id,"
                "created_at,updated_at"
            )
            .eq("lease_id", lease_id)
            .execute(),
            _REPO,
            "get",
        )
        if not rows:
            return None
        result = dict(rows[0])

        # Attach instance data as _instance key
        current_instance_id = result.get("current_instance_id")
        if current_instance_id:
            inst_rows = q.rows(
                self._instances()
                .select("instance_id,lease_id,provider_session_id,status,created_at,last_seen_at")
                .eq("instance_id", current_instance_id)
                .execute(),
                _REPO,
                "get instance",
            )
            result["_instance"] = dict(inst_rows[0]) if inst_rows else None
        else:
            result["_instance"] = None

        return result

    def create(
        self,
        lease_id: str,
        provider_name: str,
        volume_id: str | None = None,
        recipe_id: str | None = None,
        recipe_json: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        self._leases().insert(
            {
                "lease_id": lease_id,
                "provider_name": provider_name,
                "recipe_id": recipe_id,
                "recipe_json": recipe_json,
                "desired_state": "running",
                "observed_state": "detached",
                "instance_status": "detached",
                "version": 0,
                "observed_at": now,
                "last_error": None,
                "needs_refresh": 0,
                "refresh_hint_at": None,
                "status": "active",
                "volume_id": volume_id,
                "created_at": now,
                "updated_at": now,
            }
        ).execute()
        return self._require_lease(self.get(lease_id), lease_id=lease_id, operation="create")

    def find_by_instance(self, *, provider_name: str, instance_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(
                self._leases().select("lease_id").eq("provider_name", provider_name).eq("current_instance_id", instance_id),
                1,
                _REPO,
                "find_by_instance",
            ).execute(),
            _REPO,
            "find_by_instance",
        )
        if not rows:
            return None
        return self.get(str(rows[0]["lease_id"]))

    def adopt_instance(
        self,
        *,
        lease_id: str,
        provider_name: str,
        instance_id: str,
        status: str = "unknown",
    ) -> dict[str, Any]:
        from sandbox.lifecycle import parse_lease_instance_state

        existing = self.get(lease_id)
        if existing is None:
            self.create(lease_id=lease_id, provider_name=provider_name)
            existing = self._require_lease(
                self.get(lease_id),
                lease_id=lease_id,
                operation="adopt_instance bootstrap",
            )

        if existing["provider_name"] != provider_name:
            raise RuntimeError(f"Lease provider mismatch during adopt: lease={existing['provider_name']}, requested={provider_name}")

        now = _utc_now_iso()
        normalized = parse_lease_instance_state(status).value
        desired = "paused" if normalized == "paused" else "running"

        # Update the lease row
        self._leases().update(
            {
                "current_instance_id": instance_id,
                "instance_created_at": now,
                "desired_state": desired,
                "observed_state": normalized,
                "instance_status": normalized,
                "version": (existing.get("version") or 0) + 1,
                "observed_at": now,
                "last_error": None,
                "needs_refresh": True,
                "refresh_hint_at": now,
                "status": "active",
                "updated_at": now,
            }
        ).eq("lease_id", lease_id).execute()

        # Upsert instance row
        self._instances().upsert(
            {
                "instance_id": instance_id,
                "lease_id": lease_id,
                "provider_session_id": instance_id,
                "status": normalized,
                "created_at": now,
                "last_seen_at": now,
            }
        ).execute()

        return self._require_lease(self.get(lease_id), lease_id=lease_id, operation="adopt_instance")

    def mark_needs_refresh(self, lease_id: str, hint_at: Any = None) -> bool:
        from datetime import datetime as _dt

        hinted_at = (hint_at or _dt.now(UTC)).isoformat() if not isinstance(hint_at, str) else hint_at
        now = _utc_now_iso()
        response = (
            self._leases()
            .update(
                {
                    "needs_refresh": True,
                    "refresh_hint_at": hinted_at,
                    "updated_at": now,
                }
            )
            .eq("lease_id", lease_id)
            .execute()
        )
        updated = q.rows(response, _REPO, "mark_needs_refresh")
        return len(updated) > 0

    def delete(self, lease_id: str) -> None:
        self._instances().delete().eq("lease_id", lease_id).execute()
        self._leases().delete().eq("lease_id", lease_id).execute()

    def list_all(self) -> list[dict[str, Any]]:
        raw = q.rows(
            q.order(
                self._leases().select(
                    "lease_id,provider_name,recipe_id,recipe_json,current_instance_id,"
                    "desired_state,observed_state,version,created_at,updated_at"
                ),
                "created_at",
                desc=True,
                repo=_REPO,
                operation="list_all",
            ).execute(),
            _REPO,
            "list_all",
        )
        return [dict(r) for r in raw]

    def list_by_provider(self, provider_name: str) -> list[dict[str, Any]]:
        raw = q.rows(
            q.order(
                self._leases()
                .select(
                    "lease_id,provider_name,recipe_id,recipe_json,current_instance_id,"
                    "desired_state,observed_state,version,created_at,updated_at"
                )
                .eq("provider_name", provider_name),
                "created_at",
                desc=True,
                repo=_REPO,
                operation="list_by_provider",
            ).execute(),
            _REPO,
            "list_by_provider",
        )
        return [dict(r) for r in raw]
