"""Evaluation export serializers."""

from __future__ import annotations

from typing import Any


def build_batch_export(
    *,
    batch: dict[str, Any],
    aggregate: dict[str, Any],
    run_records: list[dict[str, Any]],
    export_format: str,
) -> dict[str, Any]:
    if export_format in {"predictions_json", "swe-bench-predictions"}:
        return _build_predictions_export(batch=batch, aggregate=aggregate, run_records=run_records, export_format=export_format)
    return _build_generic_export(batch=batch, aggregate=aggregate, run_records=run_records, export_format=export_format)


def _build_generic_export(
    *,
    batch: dict[str, Any],
    aggregate: dict[str, Any],
    run_records: list[dict[str, Any]],
    export_format: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "format": export_format,
        "batch": {
            "batch_id": batch.get("batch_id"),
            "kind": batch.get("kind"),
            "status": batch.get("status"),
            "config": batch.get("config_json") or {},
        },
        "aggregate": aggregate,
        "runs": run_records,
    }


def _build_predictions_export(
    *,
    batch: dict[str, Any],
    aggregate: dict[str, Any],
    run_records: list[dict[str, Any]],
    export_format: str,
) -> dict[str, Any]:
    predictions = []
    for record in run_records:
        benchmark = record.get("benchmark") or {}
        run = record.get("run") or {}
        predictions.append(
            {
                "instance_id": benchmark.get("instance_id") or record.get("scenario_id"),
                "prediction": run.get("final_response") or "",
                "run_id": run.get("run_id"),
                "scenario_id": record.get("scenario_id"),
                "judge_verdict": (record.get("judge_result") or {}).get("verdict"),
                "artifacts": record.get("artifacts") or [],
            }
        )
    return {
        "schema_version": "1",
        "format": export_format,
        "batch_id": batch.get("batch_id"),
        "aggregate": aggregate,
        "predictions": predictions,
    }
