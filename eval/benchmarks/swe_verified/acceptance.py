from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.monitor.api.http import global_router
from backend.monitor.infrastructure.evaluation import evaluation_storage_service
from eval.batch_service import EvaluationBatchService
from eval.benchmarks.swe_verified.assets import load_smoke_asset_bundle, resolve_repo_path
from eval.storage import TrajectoryStore
from storage.container import StorageContainer
from tests.fakes.supabase import FakeSupabaseClient

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
_TOKEN = "token-1"
_CLIENT = FakeSupabaseClient()
_MARKER_RE = re.compile(r"\[\[SWE_SMOKE::(?P<instance_id>[^:\]]+)::(?P<mode>pass|fail|error)\]\]")


def create_fake_supabase_client() -> FakeSupabaseClient:
    return _CLIENT


def reset_fake_supabase_client() -> FakeSupabaseClient:
    global _CLIENT
    _CLIENT = FakeSupabaseClient()
    return _CLIENT


def evaluate_smoke_judge_payload(
    *,
    instance_id: str,
    payload: dict[str, Any],
    profile_id: str = "swe_verified_pytest_smoke_gold_v1",
) -> dict[str, Any]:
    bundle = load_smoke_asset_bundle()
    known_instances = {instance.instance_id for instance in bundle.manifest.instances}
    if instance_id not in known_instances:
        raise ValueError(f"Unknown SWE-bench Verified smoke instance: {instance_id}")

    result = dict(payload.get("result") or {})
    final_response = str(result.get("final_response") or "")
    artifacts = list(result.get("artifacts") or [])
    artifact_names = {str(artifact.get("name") or "") for artifact in artifacts if isinstance(artifact, dict)}
    required_artifacts = {"final-response", "benchmark-instance", "workspace"}
    missing_artifacts = sorted(required_artifacts - artifact_names)

    passed = f"PATCH_OK::{instance_id}" in final_response and not missing_artifacts
    rationale_parts = []
    rationale_parts.append("Found patch marker." if f"PATCH_OK::{instance_id}" in final_response else "Patch marker missing.")
    if missing_artifacts:
        rationale_parts.append(f"Missing artifacts: {', '.join(missing_artifacts)}.")
    else:
        rationale_parts.append("Required artifacts present.")
    verdict = "passed" if passed else "failed"
    artifact_coverage = (len(required_artifacts) - len(missing_artifacts)) / len(required_artifacts)

    return {
        "status": "completed",
        "verdict": verdict,
        "rationale": " ".join(rationale_parts),
        "scores": {
            "resolved": 1.0 if passed else 0.0,
            "artifact_coverage": artifact_coverage,
        },
        "metadata": {
            "instance_id": instance_id,
            "judge_profile": profile_id,
            "missing_artifacts": missing_artifacts,
        },
    }


def simulate_jsonrpc_request(request: dict[str, Any]) -> dict[str, Any]:
    bundle = load_smoke_asset_bundle()
    request_id = request.get("id")
    method = str(request.get("method") or "")
    params = dict(request.get("params") or {})

    def _error(code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    if request.get("jsonrpc") != "2.0":
        return _error(-32600, "Only JSON-RPC 2.0 requests are supported.")

    if method == "eval.prepareJudgeRun":
        if params.get("benchmark") != "swe_verified":
            return _error(-32602, "benchmark must be swe_verified")
        for key in ("judge_config_path", "evaluator_input_path"):
            target = params.get(key)
            if not target or not resolve_repo_path(str(target)).exists():
                return _error(-32602, f"{key} is missing or does not exist")
        response = dict(bundle.rpc["judge_response"])
        response["id"] = request_id
        return response

    if method == "eval.previewExport":
        for key in ("contract_path", "source_slice_path"):
            target = params.get(key)
            if not target or not resolve_repo_path(str(target)).exists():
                return _error(-32602, f"{key} is missing or does not exist")
        response = dict(bundle.rpc["export_response"])
        response["id"] = request_id
        return response

    return _error(-32601, f"Unsupported method: {method}")


class _FakeAuthService:
    def verify_token(self, token: str) -> dict[str, str]:
        if token != _TOKEN:
            raise ValueError("Unknown acceptance token")
        return {"user_id": "owner-1"}


class _CreateThreadRequest(BaseModel):
    agent_user_id: str
    sandbox: str = "local"
    cwd: str | None = None


class _RunMessageRequest(BaseModel):
    message: str
    enable_trajectory: bool = True


@dataclass
class _ThreadRecord:
    thread_id: str
    agent_user_id: str
    sandbox: str
    cwd: str | None
    runtime_status: dict[str, Any] = field(default_factory=lambda: {"context": {"usage_percent": 0.42}})
    conversation: list[dict[str, Any]] = field(default_factory=list)
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    sse_events: list[dict[str, Any]] = field(default_factory=list)
    deleted: bool = False


class _ThreadHarness:
    def __init__(self) -> None:
        self._counter = 1
        self._threads: dict[str, _ThreadRecord] = {}

    def create_thread(self, payload: _CreateThreadRequest) -> str:
        thread_id = f"thread-{self._counter}"
        self._counter += 1
        self._threads[thread_id] = _ThreadRecord(
            thread_id=thread_id,
            agent_user_id=payload.agent_user_id,
            sandbox=payload.sandbox,
            cwd=payload.cwd,
        )
        return thread_id

    def run_message(self, thread_id: str, message: str) -> None:
        record = self._threads.get(thread_id)
        if record is None:
            raise KeyError(f"Thread not found: {thread_id}")

        user_text, instance_id, mode = self._parse_message(message)
        status_payload = {
            "tokens": {
                "input_tokens": 120,
                "output_tokens": 80,
                "total_tokens": 200,
                "total_cost_usd": 0.02,
            },
            "context": {"usage_percent": 0.42},
        }
        if mode == "error":
            sse_events = [
                self._sse_event(1, "status", status_payload),
                self._sse_event(2, "error", {"error": f"simulated runtime failure for {instance_id}"}),
            ]
            assistant_text = ""
        else:
            assistant_lines = [f"Inspecting repository checkout for {instance_id}."]
            if mode == "pass":
                assistant_lines.append(f"PATCH_OK::{instance_id}")
                assistant_lines.append("Focused tests: 1 passed.")
            else:
                assistant_lines.append("Unable to confirm the requested fix.")
                assistant_lines.append("Focused tests: 1 failed.")
            assistant_text = "\n".join(assistant_lines)
            sse_events = [
                self._sse_event(
                    1,
                    "tool_call",
                    {
                        "id": f"tool-{thread_id}-1",
                        "name": "inspect_repo",
                        "args": {"cwd": record.cwd or "/workspace/pytest", "instance_id": instance_id},
                    },
                ),
                self._sse_event(
                    2,
                    "tool_result",
                    {
                        "tool_call_id": f"tool-{thread_id}-1",
                        "content": f"Repository metadata collected for {instance_id}.",
                    },
                ),
                self._sse_event(3, "text", {"content": assistant_text}),
                self._sse_event(4, "status", status_payload),
                self._sse_event(5, "run_done", {"status": "completed"}),
            ]

        record.runtime_status = status_payload
        record.conversation = [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ]
        record.sse_events = sse_events
        record.trace_events = [
            {
                "seq": event["id"],
                "actor": "agent" if event["event"] != "tool_result" else "tool",
                "event_type": event["event"],
                "summary": event["event"],
                "payload": event["data"],
            }
            for event in sse_events
        ]

    def events_after(self, thread_id: str, after: int) -> list[dict[str, Any]]:
        record = self._threads.get(thread_id)
        if record is None:
            raise KeyError(f"Thread not found: {thread_id}")
        return [event for event in record.sse_events if int(event["id"]) > after]

    def runtime(self, thread_id: str) -> dict[str, Any]:
        record = self._threads.get(thread_id)
        if record is None:
            raise KeyError(f"Thread not found: {thread_id}")
        return record.runtime_status

    def delete_thread(self, thread_id: str) -> None:
        record = self._threads.get(thread_id)
        if record is None:
            raise KeyError(f"Thread not found: {thread_id}")
        record.deleted = True

    def monitor_thread_detail(self, thread_id: str) -> dict[str, Any]:
        record = self._threads.get(thread_id)
        if record is None:
            raise KeyError(f"Thread not found: {thread_id}")
        return {
            "thread": {
                "thread_id": record.thread_id,
                "agent_user_id": record.agent_user_id,
                "sandbox": record.sandbox,
                "cwd": record.cwd,
                "status": "deleted" if record.deleted else "active",
            },
            "trajectory": {
                "conversation": record.conversation,
                "events": record.trace_events,
            },
        }

    @staticmethod
    def _parse_message(message: str) -> tuple[str, str, str]:
        match = _MARKER_RE.search(message)
        if match is None:
            raise ValueError("Acceptance harness expected a [[SWE_SMOKE::<instance_id>::<mode>]] marker in the message.")
        user_text = _MARKER_RE.sub("", message, count=1).strip()
        return user_text, match.group("instance_id"), match.group("mode")

    @staticmethod
    def _sse_event(event_id: int, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": event_id, "event": event_type, "data": payload}


def create_acceptance_app() -> FastAPI:
    reset_fake_supabase_client()
    thread_harness = _ThreadHarness()
    storage_container = StorageContainer(supabase_client=create_fake_supabase_client())

    app = FastAPI(title="SWE-bench Verified Acceptance Harness")
    app.state.auth_service = _FakeAuthService()

    def _make_trajectory_store() -> TrajectoryStore:
        return TrajectoryStore(eval_repo=storage_container.eval_repo())

    def _make_eval_batch_service() -> EvaluationBatchService:
        return EvaluationBatchService(batch_repo=storage_container.evaluation_batch_repo())

    evaluation_storage_service.make_trajectory_store = _make_trajectory_store
    evaluation_storage_service.make_eval_batch_service = _make_eval_batch_service

    monitor_thread_router = APIRouter()
    thread_router = APIRouter()

    @monitor_thread_router.get("/threads")
    async def monitor_threads() -> dict[str, Any]:
        return {
            "threads": [
                {
                    "thread_id": record.thread_id,
                    "agent_user_id": record.agent_user_id,
                    "sandbox": record.sandbox,
                    "status": "deleted" if record.deleted else "active",
                }
                for record in thread_harness._threads.values()
            ]
        }

    @monitor_thread_router.get("/threads/{thread_id}")
    async def monitor_thread_detail(thread_id: str) -> dict[str, Any]:
        try:
            return thread_harness.monitor_thread_detail(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @thread_router.post("/api/threads")
    async def create_thread(payload: _CreateThreadRequest) -> dict[str, str]:
        return {"thread_id": thread_harness.create_thread(payload)}

    @thread_router.post("/api/threads/{thread_id}/messages")
    async def run_message(thread_id: str, payload: _RunMessageRequest) -> dict[str, Any]:
        try:
            thread_harness.run_message(thread_id, payload.message)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"accepted": True, "thread_id": thread_id}

    @thread_router.get("/api/threads/{thread_id}/events")
    async def stream_events(thread_id: str, after: int = Query(default=0, ge=0)) -> StreamingResponse:
        try:
            events = thread_harness.events_after(thread_id, after)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        async def _emit() -> Any:
            for event in events:
                yield f"id: {event['id']}\n".encode()
                yield f"event: {event['event']}\n".encode()
                yield f"data: {json.dumps(event['data'])}\n\n".encode()
                await asyncio.sleep(0)

        return StreamingResponse(_emit(), media_type="text/event-stream")

    @thread_router.get("/api/threads/{thread_id}/runtime")
    async def thread_runtime(thread_id: str) -> dict[str, Any]:
        try:
            return thread_harness.runtime(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @thread_router.delete("/api/threads/{thread_id}")
    async def delete_thread(thread_id: str) -> JSONResponse:
        try:
            thread_harness.delete_thread(thread_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse({"deleted": True})

    @thread_router.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(global_router.router, prefix="/api/monitor")
    app.include_router(monitor_thread_router, prefix="/api/monitor")
    app.include_router(thread_router)
    return app


def _run_judge_cli(args: argparse.Namespace) -> int:
    payload = json.load(args.stdin)
    result = evaluate_smoke_judge_payload(
        instance_id=args.instance_id,
        payload=payload,
        profile_id=args.profile_id,
    )
    print(json.dumps(result))
    return 0


def _run_rpc_cli(args: argparse.Namespace) -> int:
    with Path(args.request).open(encoding="utf-8") as handle:
        request = json.load(handle)
    print(json.dumps(simulate_jsonrpc_request(request), indent=2))
    return 0


def _run_server_cli(args: argparse.Namespace) -> int:
    logger.info("Starting SWE-bench Verified acceptance harness on port %s", args.port)
    app = create_acceptance_app()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SWE-bench Verified acceptance helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the local acceptance harness.")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(handler=_run_server_cli)

    judge = subparsers.add_parser("judge", help="Run the smoke command judge.")
    judge.add_argument("--instance-id", required=True)
    judge.add_argument("--profile-id", default="swe_verified_pytest_smoke_gold_v1")
    judge.add_argument("--stdin", type=argparse.FileType("r"), default="-")
    judge.set_defaults(handler=_run_judge_cli)

    rpc = subparsers.add_parser("rpc", help="Simulate a JSON-RPC benchmark preparation call.")
    rpc.add_argument("--request", required=True)
    rpc.set_defaults(handler=_run_rpc_cli)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
