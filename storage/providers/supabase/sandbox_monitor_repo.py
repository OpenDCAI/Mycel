"""Supabase read-only queries against the sandbox tables for monitoring."""

from __future__ import annotations

from typing import Any

from storage.providers.supabase import _query as q

_REPO = "sandbox_monitor repo"
_SANDBOX_SELECT = (
    "id,owner_user_id,provider_name,provider_env_id,sandbox_template_id,"
    "desired_state,observed_state,status,observed_at,last_error,config,created_at,updated_at"
)


class SupabaseSandboxMonitorRepo:
    """Read-only monitor queries backed by Supabase tables."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def query_threads(self, *, thread_id: str | None = None) -> list[dict]:
        q_threads = q.schema_table(
            self._client,
            "agent",
            "threads",
            _REPO,
        ).select("id,current_workspace_id,last_active_at,updated_at,created_at")
        if thread_id is not None:
            q_threads = q_threads.eq("id", thread_id)
        threads = q.rows(
            q_threads.execute(),
            _REPO,
            "query_threads threads",
        )
        if not threads:
            return []

        workspace_ids = [
            str(row.get("current_workspace_id") or "").strip() for row in threads if str(row.get("current_workspace_id") or "").strip()
        ]
        workspace_by_id = self._workspace_rows_by_id(workspace_ids)
        sandbox_ids = [
            str(workspace.get("sandbox_id") or "").strip()
            for workspace in workspace_by_id.values()
            if str(workspace.get("sandbox_id") or "").strip()
        ]
        sandbox_by_id = self._sandbox_rows_by_id(sandbox_ids, "query_threads")

        result: list[dict[str, Any]] = []
        for thread in threads:
            workspace_id = str(thread.get("current_workspace_id") or "").strip()
            workspace = workspace_by_id.get(workspace_id)
            sandbox = sandbox_by_id.get(str((workspace or {}).get("sandbox_id") or "").strip())
            lease = self._lease_row_from_sandbox(sandbox) if sandbox else None
            result.append(
                {
                    "thread_id": thread["id"],
                    "session_count": 0,
                    "sandbox_id": lease.get("sandbox_id") if lease else None,
                    "last_active": thread.get("last_active_at") or thread.get("updated_at") or thread.get("created_at"),
                    "lease_id": lease.get("lease_id") if lease else None,
                    "provider_name": lease.get("provider_name") if lease else None,
                    "desired_state": lease.get("desired_state") if lease else None,
                    "observed_state": lease.get("observed_state") if lease else None,
                    "current_instance_id": lease.get("current_instance_id") if lease else None,
                }
            )
        return sorted(result, key=lambda x: x.get("last_active") or "", reverse=True)

    def query_thread_summary(self, thread_id: str) -> dict | None:
        results = self.query_threads(thread_id=thread_id)
        return results[0] if results else None

    def query_thread_sessions(self, thread_id: str) -> list[dict]:
        # @@@monitor-session-demotion - Supabase no longer owns runtime-local chat
        # session history; remote monitor detail must not read runtime-local chat_sessions.
        return []

    def query_sandboxes(self) -> list[dict]:
        sandboxes = self._ordered_sandboxes("query_sandboxes")
        rows = [self._lease_row_from_sandbox(sandbox) for sandbox in sandboxes]
        if not rows:
            return []

        thread_by_sandbox = self._thread_id_by_sandbox_id([row["sandbox_id"] for row in rows])

        result = []
        for row in rows:
            item = dict(row)
            item["thread_id"] = thread_by_sandbox.get(row["sandbox_id"])
            result.append(item)
        return result

    def query_sandbox(self, sandbox_id: str) -> dict | None:
        sandbox_key = str(sandbox_id or "").strip()
        if not sandbox_key:
            return None
        for sandbox in self._ordered_sandboxes("query_sandbox"):
            if str(sandbox.get("id") or "").strip() == sandbox_key:
                return self._lease_row_from_sandbox(sandbox)
        return None

    def query_sandbox_sessions(self, sandbox_id: str) -> list[dict]:
        # @@@monitor-session-demotion - sandbox detail still has sandbox/thread
        # facts, but Supabase session rows are no longer admitted remote truth.
        return []

    def query_sandbox_threads(self, sandbox_id: str) -> list[dict]:
        sandbox = self.query_sandbox(sandbox_id)
        if sandbox is None:
            return []
        return [{"thread_id": thread_id} for thread_id in self._thread_ids_for_sandbox_id(sandbox_id)]

    def query_sandbox_instance_id(self, sandbox_id: str) -> str | None:
        sandbox_key = str(sandbox_id or "").strip()
        if not sandbox_key:
            return None
        return self.query_sandbox_instance_ids([sandbox_key]).get(sandbox_key)

    def query_sandbox_instance_ids(self, sandbox_ids: list[str]) -> dict[str, str | None]:
        ordered_ids = [str(sandbox_id or "").strip() for sandbox_id in sandbox_ids if str(sandbox_id or "").strip()]
        if not ordered_ids:
            return {}

        sandbox_rows = {
            str(sandbox.get("id") or "").strip(): sandbox
            for sandbox in self._ordered_sandboxes("query_sandbox_instance_ids")
            if str(sandbox.get("id") or "").strip() in ordered_ids
        }

        result: dict[str, str | None] = {}
        for sandbox_id in ordered_ids:
            sandbox = sandbox_rows.get(sandbox_id)
            if sandbox is None:
                result[sandbox_id] = None
                continue
            provider_env_id = str(sandbox.get("provider_env_id") or "").strip()
            result[sandbox_id] = provider_env_id or None
        return result

    def query_resource_sessions(self) -> list[dict]:
        sandbox_rows = self._sandbox_rows_by_runtime_bridge_lease_id("query_resource_sessions")
        result = []

        for sandbox in sandbox_rows.values():
            thread_ids = self._thread_ids_for_sandbox_id(str(sandbox.get("id") or ""))
            if thread_ids:
                for thread_id in thread_ids:
                    result.append(
                        self._resource_session_row_from_sandbox(
                            sandbox,
                            session_id=None,
                            thread_id=thread_id,
                        )
                    )
                continue

            result.append(
                self._resource_session_row_from_sandbox(
                    sandbox,
                    session_id=None,
                    thread_id=None,
                )
            )

        result.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return result

    def list_probe_targets(self) -> list[dict]:
        targets = []
        for sandbox in self._ordered_sandboxes("list_probe_targets"):
            observed_state = str(sandbox.get("observed_state") or "unknown").strip()
            if observed_state not in {"running", "detached", "paused"}:
                continue
            sandbox_id = str(sandbox.get("id") or "").strip()
            provider_name = str(sandbox.get("provider_name") or "local").strip()
            instance_id = str(sandbox.get("provider_env_id") or "").strip()
            if sandbox_id and provider_name and instance_id:
                targets.append(
                    {
                        "sandbox_id": sandbox_id,
                        "provider_name": provider_name,
                        "instance_id": instance_id,
                        "observed_state": observed_state,
                    }
                )
        return targets

    def _ordered_sandboxes(self, operation: str) -> list[dict[str, Any]]:
        query = q.order(
            q.schema_table(self._client, "container", "sandboxes", _REPO).select(_SANDBOX_SELECT),
            "updated_at",
            desc=True,
            repo=_REPO,
            operation=operation,
        )
        return q.rows(query.execute(), _REPO, operation)

    def _runtime_bridge_lease_id(self, sandbox: dict[str, Any]) -> str | None:
        config = sandbox.get("config")
        if not isinstance(config, dict):
            raise RuntimeError("sandbox.config must be an object")
        bridge_lease_id = str(config.get("legacy_lease_id") or "").strip()
        return bridge_lease_id or None

    def _sandbox_rows_by_runtime_bridge_lease_id(self, operation: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for sandbox in self._ordered_sandboxes(operation):
            bridge_lease_id = self._runtime_bridge_lease_id(sandbox)
            if not bridge_lease_id:
                continue
            result[bridge_lease_id] = sandbox
        return result

    def _workspace_rows_by_id(self, workspace_ids: list[str]) -> dict[str, dict[str, Any]]:
        ordered_ids = [str(workspace_id or "").strip() for workspace_id in workspace_ids if str(workspace_id or "").strip()]
        if not ordered_ids:
            return {}
        rows = q.rows_in_chunks(
            lambda: q.schema_table(self._client, "container", "workspaces", _REPO).select("id,sandbox_id,updated_at,created_at"),
            "id",
            ordered_ids,
            _REPO,
            "workspace_rows_by_id",
        )
        return {str(row["id"]): row for row in rows}

    def _sandbox_rows_by_id(self, sandbox_ids: list[str], operation: str) -> dict[str, dict[str, Any]]:
        ordered_ids = {str(sandbox_id or "").strip() for sandbox_id in sandbox_ids if str(sandbox_id or "").strip()}
        if not ordered_ids:
            return {}
        return {
            str(sandbox["id"]): sandbox for sandbox in self._ordered_sandboxes(operation) if str(sandbox.get("id") or "") in ordered_ids
        }

    def _thread_id_by_sandbox_id(self, sandbox_ids: list[str]) -> dict[str, str]:
        ordered_ids = [str(sandbox_id or "").strip() for sandbox_id in sandbox_ids if str(sandbox_id or "").strip()]
        if not ordered_ids:
            return {}
        sandbox_id_set = set(ordered_ids)

        # @@@monitor-binding-query - remote PostgREST can 502 on large sandbox_id IN
        # filters here; monitor already loaded all sandboxes, so filter the small
        # workspace/thread projections locally instead of making this endpoint fragile.
        workspaces = q.rows(
            q.schema_table(self._client, "container", "workspaces", _REPO).select("id,sandbox_id,updated_at,created_at").execute(),
            _REPO,
            "query_sandboxes workspaces",
        )
        workspace_to_sandbox: dict[str, str] = {}
        for row in sorted(workspaces, key=lambda x: x.get("updated_at") or x.get("created_at") or ""):
            workspace_id = str(row.get("id") or "").strip()
            sandbox_id = str(row.get("sandbox_id") or "").strip()
            if workspace_id and sandbox_id in sandbox_id_set:
                workspace_to_sandbox[workspace_id] = sandbox_id
        if not workspace_to_sandbox:
            return {}
        workspace_id_set = set(workspace_to_sandbox)

        threads = q.rows(
            q.schema_table(self._client, "agent", "threads", _REPO).select("id,current_workspace_id,updated_at,created_at").execute(),
            _REPO,
            "query_sandboxes threads",
        )
        result: dict[str, str] = {}
        for row in sorted(threads, key=lambda x: x.get("updated_at") or x.get("created_at") or ""):
            thread_id = str(row.get("id") or "").strip()
            workspace_id = str(row.get("current_workspace_id") or "").strip()
            sandbox_id = workspace_to_sandbox.get(workspace_id)
            if thread_id and workspace_id in workspace_id_set and sandbox_id:
                result[sandbox_id] = thread_id
        return result

    def _thread_ids_for_sandbox_id(self, sandbox_id: str) -> list[str]:
        sandbox_key = str(sandbox_id or "").strip()
        if not sandbox_key:
            return []
        workspaces = q.rows(
            q.order(
                q.schema_table(self._client, "container", "workspaces", _REPO)
                .select("id,sandbox_id,updated_at,created_at")
                .eq("sandbox_id", sandbox_key),
                "updated_at",
                desc=True,
                repo=_REPO,
                operation="query_sandbox_threads workspaces",
            ).execute(),
            _REPO,
            "query_sandbox_threads workspaces",
        )
        workspace_ids = [str(row.get("id") or "").strip() for row in workspaces if str(row.get("id") or "").strip()]
        if not workspace_ids:
            return []
        threads = q.rows_in_chunks(
            lambda: q.order(
                q.schema_table(self._client, "agent", "threads", _REPO).select("id,current_workspace_id,updated_at,created_at"),
                "updated_at",
                desc=True,
                repo=_REPO,
                operation="query_sandbox_threads threads",
            ),
            "current_workspace_id",
            workspace_ids,
            _REPO,
            "query_sandbox_threads threads",
        )
        seen: set[str] = set()
        result: list[str] = []
        for row in sorted(threads, key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True):
            thread_id = str(row.get("id") or "").strip()
            if thread_id and thread_id not in seen:
                seen.add(thread_id)
                result.append(thread_id)
        return result

    def _lease_row_from_sandbox(self, sandbox: dict[str, Any]) -> dict[str, Any]:
        # @@@sandbox-monitor-bridge - summary surfaces now use container.sandboxes as the
        # object truth, but still expose the lower runtime bridge while cleanup/runtime
        # residue remains lease-keyed.
        bridge_lease_id = self._runtime_bridge_lease_id(sandbox)
        return {
            "sandbox_id": str(sandbox.get("id") or "").strip() or None,
            "lease_id": bridge_lease_id,
            "provider_name": sandbox.get("provider_name"),
            "recipe_id": sandbox.get("sandbox_template_id"),
            "recipe_json": None,
            "desired_state": sandbox.get("desired_state"),
            "observed_state": sandbox.get("observed_state"),
            "current_instance_id": sandbox.get("provider_env_id"),
            "last_error": sandbox.get("last_error"),
            "updated_at": sandbox.get("updated_at"),
        }

    def _resource_session_row_from_sandbox(
        self,
        sandbox: dict[str, Any],
        *,
        session_id: str | None,
        thread_id: str | None,
    ) -> dict:
        bridge_lease_id = self._runtime_bridge_lease_id(sandbox)
        return {
            "provider": sandbox.get("provider_name") or "local",
            "session_id": session_id,
            "thread_id": thread_id,
            "sandbox_id": str(sandbox.get("id") or "").strip() or None,
            "lease_id": bridge_lease_id,
            "observed_state": sandbox.get("observed_state"),
            "desired_state": sandbox.get("desired_state"),
            "created_at": sandbox.get("created_at"),
        }
