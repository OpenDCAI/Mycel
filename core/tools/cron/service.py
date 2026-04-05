"""CronToolService — agent-callable cron job CRUD on top of existing backend service."""

from __future__ import annotations

import json
from typing import Any

from croniter import croniter

from backend.web.services import cron_job_service
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema

CRON_CREATE_SCHEMA = make_tool_schema(
    name="CronCreate",
    description="Create a cron job using the existing Mycel cron_jobs substrate.",
    properties={
        "name": {"type": "string", "description": "Human-readable cron job name", "minLength": 1},
        "cron_expression": {
            "type": "string",
            "description": "Standard 5-field cron expression",
            "minLength": 1,
        },
        "description": {"type": "string", "description": "Optional cron job description"},
        "task_template": {
            "type": "string",
            "description": "JSON string template used when the cron job creates a task",
        },
        "enabled": {"type": "boolean", "description": "Whether the cron job starts enabled"},
    },
    required=["name", "cron_expression"],
)

CRON_DELETE_SCHEMA = make_tool_schema(
    name="CronDelete",
    description="Delete a cron job by ID.",
    properties={
        "job_id": {"type": "string", "description": "Cron job ID returned by CronCreate", "minLength": 1},
    },
    required=["job_id"],
)

CRON_LIST_SCHEMA = make_tool_schema(
    name="CronList",
    description="List all cron jobs in the current Mycel cron_jobs substrate.",
    properties={},
)


class CronToolService:
    def __init__(self, registry: ToolRegistry):
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        for name, schema, handler, read_only in [
            ("CronCreate", CRON_CREATE_SCHEMA, self._create, False),
            ("CronDelete", CRON_DELETE_SCHEMA, self._delete, False),
            ("CronList", CRON_LIST_SCHEMA, self._list, True),
        ]:
            registry.register(
                ToolEntry(
                    name=name,
                    mode=ToolMode.DEFERRED,
                    schema=schema,
                    handler=handler,
                    source="CronToolService",
                    is_concurrency_safe=read_only,
                    is_read_only=read_only,
                )
            )

    def _create(self, **args: Any) -> str:
        name = str(args.get("name", "")).strip()
        cron_expression = str(args.get("cron_expression", "")).strip()
        if not croniter.is_valid(cron_expression):
            raise ValueError(f"Invalid cron expression: {cron_expression!r}")

        task_template = args.get("task_template", "{}")
        if isinstance(task_template, str):
            try:
                json.loads(task_template)
            except json.JSONDecodeError as exc:
                raise ValueError("task_template must be valid JSON") from exc

        item = cron_job_service.create_cron_job(
            name=name,
            cron_expression=cron_expression,
            description=str(args.get("description", "")),
            task_template=task_template,
            enabled=int(bool(args.get("enabled", True))),
        )
        return json.dumps({"item": item}, ensure_ascii=False, indent=2)

    def _delete(self, **args: Any) -> str:
        job_id = str(args.get("job_id", "")).strip()
        ok = cron_job_service.delete_cron_job(job_id)
        if not ok:
            raise ValueError(f"Cron job not found: {job_id}")
        return json.dumps({"ok": True, "id": job_id}, ensure_ascii=False, indent=2)

    def _list(self, **_args: Any) -> str:
        items = cron_job_service.list_cron_jobs()
        return json.dumps({"items": items, "total": len(items)}, ensure_ascii=False, indent=2)
