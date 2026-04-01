"""Supabase repository for run event persistence operations."""

from __future__ import annotations

import json
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "run event repo"
_TABLE = "run_events"


class SupabaseRunEventRepo:
    """Minimal run event repository backed by a Supabase client."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def append_event(
        self,
        thread_id: str,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
        message_id: str | None = None,
    ) -> int:
        response = (
            self._t()
            .insert(
                {
                    "thread_id": thread_id,
                    "run_id": run_id,
                    "event_type": event_type,
                    "data": json.dumps(data, ensure_ascii=False),
                    "message_id": message_id,
                }
            )
            .execute()
        )
        inserted = q.rows(response, _REPO, "append_event")
        if not inserted:
            raise RuntimeError("Supabase run event repo expected inserted row for append_event. Check table permissions.")
        seq = inserted[0].get("seq")
        if seq is None:
            raise RuntimeError("Supabase run event repo expected non-null seq in append_event response. Check run_events table schema.")
        return int(seq)

    def list_events(
        self,
        thread_id: str,
        run_id: str,
        *,
        after: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = q.limit(
            q.order(
                q.gt(
                    self._t().select("seq,event_type,data,message_id").eq("thread_id", thread_id).eq("run_id", run_id),
                    "seq",
                    after,
                    _REPO,
                    "list_events",
                ),
                "seq",
                desc=False,
                repo=_REPO,
                operation="list_events",
            ),
            limit,
            _REPO,
            "list_events",
        )
        raw_rows = q.rows(query.execute(), _REPO, "list_events")

        events: list[dict[str, Any]] = []
        for row in raw_rows:
            seq = row.get("seq")
            if seq is None:
                raise RuntimeError("Supabase run event repo expected non-null seq in list_events row. Check run_events table schema.")
            payload = row.get("data")
            if payload in (None, ""):
                parsed: dict[str, Any] = {}
            elif isinstance(payload, str):
                try:
                    loaded = json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Supabase run event repo expected valid JSON in list_events data: {exc}.") from exc
                if not isinstance(loaded, dict):
                    raise RuntimeError(f"Supabase run event repo expected dict JSON in list_events, got {type(loaded).__name__}.")
                parsed = loaded
            elif isinstance(payload, dict):
                parsed = payload
            else:
                raise RuntimeError(f"Supabase run event repo expected str or dict data in list_events, got {type(payload).__name__}.")

            message_id = row.get("message_id")
            if message_id is not None and not isinstance(message_id, str):
                raise RuntimeError(f"Supabase run event repo expected message_id to be str or null, got {type(message_id).__name__}.")
            events.append(
                {
                    "seq": int(seq),
                    "event_type": str(row.get("event_type") or ""),
                    "data": parsed,
                    "message_id": message_id,
                }
            )
        return events

    def latest_seq(self, thread_id: str) -> int:
        query = q.limit(
            q.order(self._t().select("seq").eq("thread_id", thread_id), "seq", desc=True, repo=_REPO, operation="latest_seq"),
            1,
            _REPO,
            "latest_seq",
        )
        rows = q.rows(query.execute(), _REPO, "latest_seq")
        if not rows:
            return 0
        seq = rows[0].get("seq")
        if seq is None:
            raise RuntimeError("Supabase run event repo expected non-null seq in latest_seq row. Check run_events table schema.")
        return int(seq)

    def run_start_seq(self, thread_id: str, run_id: str) -> int:
        query = q.limit(
            q.order(
                self._t().select("seq").eq("thread_id", thread_id).eq("run_id", run_id),
                "seq",
                desc=False,
                repo=_REPO,
                operation="run_start_seq",
            ),
            1,
            _REPO,
            "run_start_seq",
        )
        rows = q.rows(query.execute(), _REPO, "run_start_seq")
        if not rows:
            return 0
        seq = rows[0].get("seq")
        return int(seq) if seq is not None else 0

    def latest_run_id(self, thread_id: str) -> str | None:
        query = q.limit(
            q.order(
                self._t().select("run_id,seq").eq("thread_id", thread_id),
                "seq",
                desc=True,
                repo=_REPO,
                operation="latest_run_id",
            ),
            1,
            _REPO,
            "latest_run_id",
        )
        rows = q.rows(query.execute(), _REPO, "latest_run_id")
        if not rows:
            return None
        run_id = rows[0].get("run_id")
        return str(run_id) if run_id else None

    def list_run_ids(self, thread_id: str) -> list[str]:
        query = q.order(
            self._t().select("run_id,seq").eq("thread_id", thread_id),
            "seq",
            desc=True,
            repo=_REPO,
            operation="list_run_ids",
        )
        raw_rows = q.rows(query.execute(), _REPO, "list_run_ids")

        run_ids: list[str] = []
        seen: set[str] = set()
        # @@@run-id-ordering - latest seq first, deduped by first sighting.
        for row in raw_rows:
            run_id = row.get("run_id")
            if not run_id:
                continue
            rid = str(run_id)
            if rid in seen:
                continue
            seen.add(rid)
            run_ids.append(rid)
        return run_ids

    def delete_runs(self, thread_id: str, run_ids: list[str]) -> int:
        if not run_ids:
            return 0
        pre = q.rows(
            q.in_(self._t().select("seq").eq("thread_id", thread_id), "run_id", run_ids, _REPO, "delete_runs").execute(),
            _REPO,
            "delete_runs pre-count",
        )
        q.in_(self._t().delete().eq("thread_id", thread_id), "run_id", run_ids, _REPO, "delete_runs").execute()
        return len(pre)

    def delete_thread_events(self, thread_id: str) -> int:
        pre = q.rows(self._t().select("seq").eq("thread_id", thread_id).execute(), _REPO, "delete_thread_events")
        self._t().delete().eq("thread_id", thread_id).execute()
        return len(pre)

    def _t(self) -> Any:
        return self._client.table(_TABLE)
