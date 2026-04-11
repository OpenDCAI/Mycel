"""Eval harness client for the current public thread API."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from eval.models import TrajectoryCapture


class EvalClient:
    """HTTP + SSE client for driving Leon agent evaluation."""

    def __init__(self, base_url: str = "http://localhost:8001", token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token or None
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=300.0, trust_env=False)
        self._thread_event_cursors: dict[str, int] = {}

    def _auth_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    async def create_thread(
        self,
        agent_user_id: str | None = None,
        sandbox: str = "local",
        cwd: str | None = None,
    ) -> str:
        """Create a new thread. Returns thread_id."""
        resolved_agent_user_id = agent_user_id or os.getenv("LEON_EVAL_AGENT_USER_ID")
        if not resolved_agent_user_id:
            raise RuntimeError("EvalClient.create_thread requires agent_user_id or LEON_EVAL_AGENT_USER_ID")
        payload: dict[str, Any] = {"agent_user_id": resolved_agent_user_id, "sandbox": sandbox}
        if cwd:
            payload["cwd"] = cwd
        resp = await self._client.post("/api/threads", json=payload, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()["thread_id"]

    async def run_message(
        self,
        thread_id: str,
        message: str,
        enable_trajectory: bool = True,
    ) -> TrajectoryCapture:
        """Start a public thread run, then consume its thread event stream."""
        capture = TrajectoryCapture()
        payload = {"message": message, "enable_trajectory": enable_trajectory}
        headers = self._auth_headers()
        start_resp = await self._client.post(
            f"/api/threads/{thread_id}/messages",
            json=payload,
            headers=headers,
        )
        start_resp.raise_for_status()

        after = self._thread_event_cursors.get(thread_id, 0)
        stream_path = f"/api/threads/{thread_id}/events?after={after}"
        if self.token:
            stream_path = f"{stream_path}&token={self.token}"

        # @@@public-thread-sse-handoff - the current public contract starts a run
        # with POST /messages, then delivers lifecycle/text over persistent
        # thread events. The harness must mirror that path exactly or it will
        # prove a dead API instead of real runtime truth.
        async with self._client.stream(
            "GET",
            stream_path,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            event_type = ""
            data_buf = ""
            event_id: int | None = None

            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    data_buf = ""
                elif line.startswith("id:"):
                    try:
                        event_id = int(line[3:].strip())
                    except ValueError:
                        event_id = None
                elif line.startswith("data:"):
                    data_buf = line[5:].strip()
                elif line == "" and event_type and data_buf:
                    # End of SSE event
                    self._process_event(capture, event_type, data_buf)
                    if event_id is not None:
                        self._thread_event_cursors[thread_id] = event_id
                    if event_type in ("run_done", "cancelled", "error"):
                        break
                    event_type = ""
                    data_buf = ""
                    event_id = None

        return capture

    def _process_event(self, capture: TrajectoryCapture, event_type: str, data: str) -> None:
        """Route an SSE event into the appropriate capture bucket."""
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = {"raw": data}

        if event_type == "text":
            content = parsed.get("content", "")
            if content:
                capture.text_chunks.append(content)
        elif event_type == "tool_call":
            capture.tool_calls.append(parsed)
        elif event_type == "tool_result":
            capture.tool_results.append(parsed)
        elif event_type == "status":
            capture.status_snapshots.append(parsed)
            capture.final_status = parsed
        elif event_type == "run_done":
            capture.terminal_event = "done"
        elif event_type in ("cancelled", "error"):
            capture.terminal_event = event_type
            if event_type == "error":
                capture.final_status = parsed

    async def get_runtime(self, thread_id: str) -> dict:
        """Get runtime status for a thread."""
        resp = await self._client.get(f"/api/threads/{thread_id}/runtime", headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def delete_thread(self, thread_id: str) -> None:
        """Delete a thread and its resources."""
        resp = await self._client.delete(f"/api/threads/{thread_id}", headers=self._auth_headers())
        resp.raise_for_status()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
