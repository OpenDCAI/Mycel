"""Supabase read-only queries against the sandbox tables for monitoring."""

from __future__ import annotations

from typing import Any

from storage.providers.supabase import _query as q

_REPO = "sandbox_monitor repo"


class SupabaseSandboxMonitorRepo:
    """Read-only monitor queries backed by Supabase tables."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def query_threads(self, *, thread_id: str | None = None) -> list[dict]:
        # Fetch active chat_sessions joined with sandbox_leases via lease_id
        q_sessions = self._client.table("chat_sessions").select("thread_id,chat_session_id,last_active_at,lease_id").neq("status", "closed")
        if thread_id is not None:
            q_sessions = q_sessions.eq("thread_id", thread_id)
        sessions = q.rows(
            q_sessions.execute(),
            _REPO,
            "query_threads sessions",
        )
        if not sessions:
            return []

        lease_ids = list({s["lease_id"] for s in sessions if s.get("lease_id")})
        lease_map: dict[str, dict] = {}
        if lease_ids:
            leases = q.rows(
                q.in_(
                    self._client.table("sandbox_leases").select("lease_id,provider_name,desired_state,observed_state,current_instance_id"),
                    "lease_id",
                    lease_ids,
                    _REPO,
                    "query_threads leases",
                ).execute(),
                _REPO,
                "query_threads leases",
            )
            lease_map = {le["lease_id"]: le for le in leases}

        # Aggregate per thread_id
        by_thread: dict[str, dict] = {}
        for s in sessions:
            tid = s["thread_id"]
            last_active = s.get("last_active_at")
            lease = lease_map.get(s.get("lease_id") or "")
            if tid not in by_thread:
                by_thread[tid] = {
                    "thread_id": tid,
                    "session_count": 0,
                    "last_active": last_active,
                    "lease_id": s.get("lease_id"),
                    "provider_name": lease.get("provider_name") if lease else None,
                    "desired_state": lease.get("desired_state") if lease else None,
                    "observed_state": lease.get("observed_state") if lease else None,
                    "current_instance_id": lease.get("current_instance_id") if lease else None,
                }
            by_thread[tid]["session_count"] += 1
            if last_active and (not by_thread[tid]["last_active"] or last_active > by_thread[tid]["last_active"]):
                by_thread[tid]["last_active"] = last_active

        return sorted(by_thread.values(), key=lambda x: x.get("last_active") or "", reverse=True)

    def query_thread_summary(self, thread_id: str) -> dict | None:
        results = self.query_threads(thread_id=thread_id)
        return results[0] if results else None

    def query_thread_sessions(self, thread_id: str) -> list[dict]:
        sessions = q.rows(
            q.order(
                self._client.table("chat_sessions")
                .select("chat_session_id,status,started_at,ended_at,close_reason,lease_id")
                .eq("thread_id", thread_id),
                "started_at",
                desc=True,
                repo=_REPO,
                operation="query_thread_sessions",
            ).execute(),
            _REPO,
            "query_thread_sessions",
        )
        if not sessions:
            return []

        lease_ids = list({s["lease_id"] for s in sessions if s.get("lease_id")})
        lease_map: dict[str, dict] = {}
        if lease_ids:
            leases = q.rows(
                q.in_(
                    self._client.table("sandbox_leases").select(
                        "lease_id,provider_name,desired_state,observed_state,current_instance_id,last_error"
                    ),
                    "lease_id",
                    lease_ids,
                    _REPO,
                    "query_thread_sessions leases",
                ).execute(),
                _REPO,
                "query_thread_sessions leases",
            )
            lease_map = {le["lease_id"]: le for le in leases}

        result = []
        for s in sessions:
            lease = lease_map.get(s.get("lease_id") or "")
            result.append(
                {
                    "chat_session_id": s["chat_session_id"],
                    "status": s.get("status"),
                    "started_at": s.get("started_at"),
                    "ended_at": s.get("ended_at"),
                    "close_reason": s.get("close_reason"),
                    "lease_id": s.get("lease_id"),
                    "provider_name": lease.get("provider_name") if lease else None,
                    "desired_state": lease.get("desired_state") if lease else None,
                    "observed_state": lease.get("observed_state") if lease else None,
                    "current_instance_id": lease.get("current_instance_id") if lease else None,
                    "last_error": lease.get("last_error") if lease else None,
                }
            )
        return result

    def query_leases(self) -> list[dict]:
        leases = q.rows(
            q.order(
                self._client.table("sandbox_leases").select(
                    "lease_id,provider_name,recipe_id,recipe_json,desired_state,observed_state,current_instance_id,last_error,updated_at"
                ),
                "updated_at",
                desc=True,
                repo=_REPO,
                operation="query_leases",
            ).execute(),
            _REPO,
            "query_leases",
        )
        if not leases:
            return []

        lease_ids = [le["lease_id"] for le in leases]
        terminals = q.rows(
            q.in_(
                self._client.table("abstract_terminals").select("lease_id,thread_id,created_at"),
                "lease_id",
                lease_ids,
                _REPO,
                "query_leases terminals",
            ).execute(),
            _REPO,
            "query_leases terminals",
        )
        # Pick most recent terminal per lease
        term_map: dict[str, str] = {}
        for t in sorted(terminals, key=lambda x: x.get("created_at") or ""):
            term_map[t["lease_id"]] = t["thread_id"]

        result = []
        for lease in leases:
            row = dict(lease)
            row["thread_id"] = term_map.get(lease["lease_id"])
            result.append(row)
        return result

    def list_leases_with_threads(self) -> list[dict]:
        return self.query_leases()

    def query_lease(self, lease_id: str) -> dict | None:
        rows = q.rows(
            self._client.table("sandbox_leases").select("*").eq("lease_id", lease_id).execute(),
            _REPO,
            "query_lease",
        )
        return dict(rows[0]) if rows else None

    def query_lease_sessions(self, lease_id: str) -> list[dict]:
        sessions = q.rows(
            q.order(
                self._client.table("chat_sessions")
                .select("chat_session_id,thread_id,status,started_at,ended_at,close_reason,lease_id")
                .eq("lease_id", lease_id),
                "started_at",
                desc=True,
                repo=_REPO,
                operation="query_lease_sessions",
            ).execute(),
            _REPO,
            "query_lease_sessions",
        )
        lease = self.query_lease(lease_id)
        return [
            {
                "chat_session_id": session.get("chat_session_id"),
                "thread_id": session.get("thread_id"),
                "status": session.get("status"),
                "started_at": session.get("started_at"),
                "ended_at": session.get("ended_at"),
                "close_reason": session.get("close_reason"),
                "lease_id": session.get("lease_id"),
                "provider_name": lease.get("provider_name") if lease else None,
                "desired_state": lease.get("desired_state") if lease else None,
                "observed_state": lease.get("observed_state") if lease else None,
                "current_instance_id": lease.get("current_instance_id") if lease else None,
                "last_error": lease.get("last_error") if lease else None,
            }
            for session in sessions
        ]

    def query_lease_threads(self, lease_id: str) -> list[dict]:
        rows = q.rows(
            q.order(
                self._client.table("abstract_terminals").select("thread_id").eq("lease_id", lease_id),
                "created_at",
                desc=True,
                repo=_REPO,
                operation="query_lease_threads",
            ).execute(),
            _REPO,
            "query_lease_threads",
        )
        seen: set[str] = set()
        result = []
        for r in rows:
            if r["thread_id"] not in seen:
                seen.add(r["thread_id"])
                result.append({"thread_id": r["thread_id"]})
        return result

    def query_lease_events(self, lease_id: str) -> list[dict]:
        # provider_events is the Supabase equivalent
        rows = q.rows(
            q.order(
                self._client.table("provider_events").select("*").eq("matched_lease_id", lease_id),
                "created_at",
                desc=True,
                repo=_REPO,
                operation="query_lease_events",
            ).execute(),
            _REPO,
            "query_lease_events",
        )
        return [dict(r) for r in rows]

    def list_sessions_with_leases(self) -> list[dict]:
        active_sessions = q.rows(
            self._client.table("chat_sessions").select("chat_session_id,thread_id,lease_id,started_at").neq("status", "closed").execute(),
            _REPO,
            "list_sessions_with_leases active",
        )

        # All leases (for terminal fallback)
        leases = q.rows(
            self._client.table("sandbox_leases").select("lease_id,provider_name,observed_state,desired_state,created_at").execute(),
            _REPO,
            "list_sessions_with_leases leases",
        )
        lease_map = {le["lease_id"]: le for le in leases}

        all_terminals = q.rows(
            self._client.table("abstract_terminals").select("lease_id,thread_id,created_at").execute(),
            _REPO,
            "list_sessions_with_leases terminals",
        )
        terminal_rows_by_lease: dict[str, list[dict[str, Any]]] = {}
        for row in all_terminals:
            terminal_rows_by_lease.setdefault(str(row.get("lease_id") or ""), []).append(dict(row))

        all_sessions = q.rows(
            self._client.table("chat_sessions").select("chat_session_id,thread_id,lease_id,status,started_at").execute(),
            _REPO,
            "list_sessions_with_leases all_sessions",
        )
        latest_session_thread_by_lease: dict[str, str] = {}
        for row in sorted(all_sessions, key=lambda x: x.get("started_at") or ""):
            lease_id = str(row.get("lease_id") or "")
            thread_id = str(row.get("thread_id") or "")
            if lease_id and thread_id:
                latest_session_thread_by_lease[lease_id] = thread_id

        result = []
        seen_leases: set[str] = set()

        for s in active_sessions:
            lease = lease_map.get(s.get("lease_id") or "")
            if not lease:
                continue
            seen_leases.add(lease["lease_id"])
            result.append(
                {
                    "provider": lease.get("provider_name") or "local",
                    "session_id": s["chat_session_id"],
                    "thread_id": s["thread_id"],
                    "lease_id": lease["lease_id"],
                    "observed_state": lease.get("observed_state"),
                    "desired_state": lease.get("desired_state"),
                    "created_at": lease.get("created_at"),
                }
            )

        for lease in leases:
            lid = lease["lease_id"]
            if lid in seen_leases:
                continue
            terminal_rows = terminal_rows_by_lease.get(lid, [])
            if terminal_rows:
                for terminal_row in terminal_rows:
                    result.append(
                        {
                            "provider": lease.get("provider_name") or "local",
                            "session_id": None,
                            "thread_id": terminal_row.get("thread_id"),
                            "lease_id": lid,
                            "observed_state": lease.get("observed_state"),
                            "desired_state": lease.get("desired_state"),
                            "created_at": lease.get("created_at"),
                        }
                    )
                continue

            result.append(
                {
                    "provider": lease.get("provider_name") or "local",
                    "session_id": None,
                    "thread_id": latest_session_thread_by_lease.get(lid),
                    "lease_id": lid,
                    "observed_state": lease.get("observed_state"),
                    "desired_state": lease.get("desired_state"),
                    "created_at": lease.get("created_at"),
                }
            )

        result.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return result

    def list_probe_targets(self) -> list[dict]:
        leases = q.rows(
            q.order(
                self._client.table("sandbox_leases")
                .select("lease_id,provider_name,current_instance_id,observed_state,updated_at")
                .in_("observed_state", ["running", "detached", "paused"]),
                "updated_at",
                desc=True,
                repo=_REPO,
                operation="list_probe_targets",
            ).execute(),
            _REPO,
            "list_probe_targets",
        )

        # Try sandbox_instances for provider_session_id
        instance_map: dict[str, str] = {}
        instances = q.rows(
            self._client.table("sandbox_instances").select("lease_id,provider_session_id").execute(),
            _REPO,
            "list_probe_targets instances",
        )
        for inst in instances:
            if inst.get("provider_session_id"):
                instance_map[inst["lease_id"]] = inst["provider_session_id"]

        targets = []
        for lease in leases:
            lid = lease["lease_id"]
            instance_id = instance_map.get(lid) or lease.get("current_instance_id") or ""
            if lid and lease.get("provider_name") and instance_id:
                targets.append(
                    {
                        "lease_id": lid,
                        "provider_name": lease["provider_name"],
                        "instance_id": instance_id,
                        "observed_state": lease.get("observed_state", "unknown"),
                    }
                )
        return targets

    def query_lease_instance_id(self, lease_id: str) -> str | None:
        return self.query_lease_instance_ids([lease_id]).get(lease_id)

    def query_lease_instance_ids(self, lease_ids: list[str]) -> dict[str, str | None]:
        ordered_ids = [str(lease_id or "").strip() for lease_id in lease_ids if str(lease_id or "").strip()]
        if not ordered_ids:
            return {}

        instance_map: dict[str, str | None] = {lease_id: None for lease_id in ordered_ids}
        instances = q.rows(
            q.in_(
                self._client.table("sandbox_instances").select("lease_id,provider_session_id"),
                "lease_id",
                ordered_ids,
                _REPO,
                "query_lease_instance_ids instances",
            ).execute(),
            _REPO,
            "query_lease_instance_ids instances",
        )
        for row in instances:
            lease_id = str(row.get("lease_id") or "").strip()
            provider_session_id = str(row.get("provider_session_id") or "").strip()
            if lease_id and provider_session_id:
                instance_map[lease_id] = provider_session_id

        missing_ids = [lease_id for lease_id, instance_id in instance_map.items() if not instance_id]
        if not missing_ids:
            return instance_map

        leases = q.rows(
            q.in_(
                self._client.table("sandbox_leases").select("lease_id,current_instance_id"),
                "lease_id",
                missing_ids,
                _REPO,
                "query_lease_instance_ids leases",
            ).execute(),
            _REPO,
            "query_lease_instance_ids leases",
        )
        for row in leases:
            lease_id = str(row.get("lease_id") or "").strip()
            current_instance_id = str(row.get("current_instance_id") or "").strip()
            if lease_id and current_instance_id:
                instance_map[lease_id] = current_instance_id
        return instance_map
