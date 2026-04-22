from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_ROOT = Path(__file__).resolve().parent / "smoke"


class SmokeBenchmark(BaseModel):
    family: str
    dataset_name: str
    dataset_split: str
    dataset_revision: str
    source_urls: dict[str, str] = Field(default_factory=dict)


class SmokeSelection(BaseModel):
    repo: str
    environment_setup_commit: str
    max_instances: int
    selection_rules: list[str] = Field(default_factory=list)


class SmokeJudgeHints(BaseModel):
    prediction_key: str
    success_requirements: list[str] = Field(default_factory=list)
    prediction_format: dict[str, str] = Field(default_factory=dict)


class SmokeRuntimeHints(BaseModel):
    checkout_url: str
    working_directory: str
    language: str


class SmokeInstance(BaseModel):
    instance_id: str
    repo: str
    base_commit: str
    environment_setup_commit: str
    difficulty: str
    created_at: str
    version: str
    problem_statement: str
    hints_text: str = ""
    fail_to_pass: list[str] = Field(default_factory=list)
    pass_to_pass: list[str] = Field(default_factory=list)
    fail_to_pass_count: int
    pass_to_pass_count: int
    official_patch_path: str
    official_patch_sha256: str
    official_test_patch_path: str
    official_test_patch_sha256: str
    judge: SmokeJudgeHints
    runtime: SmokeRuntimeHints
    selection_rank: int


class SmokeManifest(BaseModel):
    slice_id: str
    benchmark: SmokeBenchmark
    selection: SmokeSelection
    instances: list[SmokeInstance] = Field(default_factory=list)


class OfficialEvaluatorConfig(BaseModel):
    module: str
    command_template: list[str] = Field(default_factory=list)
    prediction_format: str
    required_prediction_fields: list[str] = Field(default_factory=list)
    gold_predictions_supported: bool = False


class JudgeScoringConfig(BaseModel):
    resolved_field: str
    required_test_sets: list[str] = Field(default_factory=list)
    failure_policy: str


class JudgeArtifactsConfig(BaseModel):
    prediction_records_path: str
    export_contract_path: str
    golden_export_path: str


class JudgeConfig(BaseModel):
    profile_id: str
    benchmark: str
    slice_manifest_path: str
    dataset_name: str
    dataset_split: str
    dataset_revision: str
    repo: str
    environment_setup_commit: str
    instance_ids: list[str] = Field(default_factory=list)
    official_evaluator: OfficialEvaluatorConfig
    scoring: JudgeScoringConfig
    artifacts: JudgeArtifactsConfig


class SampleEvaluatorInput(BaseModel):
    judge_profile: str
    slice_id: str
    run_id: str
    max_workers: int
    dataset_name: str
    dataset_split: str
    dataset_revision: str
    repo: str
    environment_setup_commit: str
    instance_ids: list[str] = Field(default_factory=list)
    predictions_path: str
    official_patch_mode: str


class ExportContract(BaseModel):
    contract_id: str
    description: str
    top_level_required: list[str] = Field(default_factory=list)
    instance_required: list[str] = Field(default_factory=list)
    prediction_record_required: list[str] = Field(default_factory=list)
    judge_inputs_required: list[str] = Field(default_factory=list)
    judge_result_required: list[str] = Field(default_factory=list)
    artifacts_required: list[str] = Field(default_factory=list)


@dataclass
class SmokeAssetBundle:
    manifest: SmokeManifest
    judge_config: JudgeConfig
    sample_evaluator_input: SampleEvaluatorInput
    export_contract: ExportContract
    export_golden: dict[str, Any]
    predictions: list[dict[str, Any]]
    rpc: dict[str, dict[str, Any]]


def resolve_repo_path(path: str) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = REPO_ROOT / resolved
    return resolved


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def load_smoke_asset_bundle(smoke_root: Path = SMOKE_ROOT) -> SmokeAssetBundle:
    manifest = SmokeManifest.model_validate(_load_json(smoke_root / "manifest.json"))
    judge_config = JudgeConfig.model_validate(_load_json(smoke_root / "judge_config.json"))
    sample_evaluator_input = SampleEvaluatorInput.model_validate(_load_json(smoke_root / "sample_evaluator_input.json"))
    export_contract = ExportContract.model_validate(_load_json(smoke_root / "export_contract.json"))
    export_golden = _load_json(smoke_root / "export_golden.json")
    predictions = _load_jsonl(smoke_root / "sample_predictions.jsonl")
    rpc = {
        "judge_request": _load_json(smoke_root / "rpc/judge_request.json"),
        "judge_response": _load_json(smoke_root / "rpc/judge_response.json"),
        "export_request": _load_json(smoke_root / "rpc/export_request.json"),
        "export_response": _load_json(smoke_root / "rpc/export_response.json"),
    }
    return SmokeAssetBundle(
        manifest=manifest,
        judge_config=judge_config,
        sample_evaluator_input=sample_evaluator_input,
        export_contract=export_contract,
        export_golden=export_golden,
        predictions=predictions,
        rpc=rpc,
    )


def clone_bundle(bundle: SmokeAssetBundle) -> SmokeAssetBundle:
    return copy.deepcopy(bundle)


def _sha256_for_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_keys(payload: dict[str, Any], required: list[str], *, label: str, issues: list[str]) -> None:
    missing = [key for key in required if key not in payload]
    if missing:
        issues.append(f"{label} missing keys: {', '.join(missing)}")


def validate_smoke_assets(bundle: SmokeAssetBundle) -> list[str]:
    issues: list[str] = []
    manifest = bundle.manifest
    instance_ids = [instance.instance_id for instance in manifest.instances]

    if not manifest.instances:
        issues.append("manifest must contain at least one instance")
        return issues

    if len(instance_ids) != len(set(instance_ids)):
        issues.append("manifest contains duplicate instance_id values")

    if len(manifest.instances) > manifest.selection.max_instances:
        issues.append("manifest exceeds selection.max_instances")

    if bundle.judge_config.instance_ids != instance_ids:
        issues.append("judge config instance_ids do not match manifest order")

    if bundle.sample_evaluator_input.instance_ids != instance_ids:
        issues.append("sample evaluator input instance_ids do not match manifest order")

    if bundle.judge_config.profile_id != bundle.sample_evaluator_input.judge_profile:
        issues.append("judge profile mismatch between judge_config and sample_evaluator_input")

    if bundle.judge_config.dataset_name != manifest.benchmark.dataset_name:
        issues.append("judge config dataset_name does not match manifest")

    if bundle.judge_config.dataset_revision != manifest.benchmark.dataset_revision:
        issues.append("judge config dataset_revision does not match manifest")

    if bundle.sample_evaluator_input.dataset_name != manifest.benchmark.dataset_name:
        issues.append("sample evaluator input dataset_name does not match manifest")

    if bundle.sample_evaluator_input.dataset_revision != manifest.benchmark.dataset_revision:
        issues.append("sample evaluator input dataset_revision does not match manifest")

    if bundle.sample_evaluator_input.max_workers != 1:
        issues.append("sample evaluator input must pin max_workers to 1 for smoke validation")

    predictions_path = resolve_repo_path(bundle.sample_evaluator_input.predictions_path)
    if not predictions_path.exists():
        issues.append(f"sample predictions file is missing: {predictions_path}")

    if len(bundle.predictions) != len(manifest.instances):
        issues.append("sample predictions line count does not match manifest instances")

    prediction_lookup = {record.get("instance_id"): record for record in bundle.predictions}
    if list(prediction_lookup) != instance_ids:
        issues.append("sample predictions instance_ids do not match manifest order")

    for instance in manifest.instances:
        if instance.repo != manifest.selection.repo:
            issues.append(f"{instance.instance_id} repo does not match slice repo")
        if instance.environment_setup_commit != manifest.selection.environment_setup_commit:
            issues.append(f"{instance.instance_id} environment_setup_commit does not match slice pin")
        if instance.fail_to_pass_count != len(instance.fail_to_pass):
            issues.append(f"{instance.instance_id} fail_to_pass_count is inconsistent")
        if instance.pass_to_pass_count != len(instance.pass_to_pass):
            issues.append(f"{instance.instance_id} pass_to_pass_count is inconsistent")
        if not instance.fail_to_pass:
            issues.append(f"{instance.instance_id} must include at least one FAIL_TO_PASS test")
        if instance.judge.prediction_key != instance.instance_id:
            issues.append(f"{instance.instance_id} judge prediction_key must equal instance_id")
        if set(instance.judge.prediction_format) != {"instance_id", "model_name_or_path", "model_patch"}:
            issues.append(f"{instance.instance_id} prediction_format keys are incomplete")

        patch_path = resolve_repo_path(instance.official_patch_path)
        test_patch_path = resolve_repo_path(instance.official_test_patch_path)
        if not patch_path.exists():
            issues.append(f"{instance.instance_id} patch fixture is missing: {patch_path}")
        else:
            actual_patch_sha = _sha256_for_path(patch_path)
            if actual_patch_sha != instance.official_patch_sha256:
                issues.append(f"{instance.instance_id} patch fixture sha256 mismatch")
        if not test_patch_path.exists():
            issues.append(f"{instance.instance_id} test patch fixture is missing: {test_patch_path}")
        else:
            actual_test_patch_sha = _sha256_for_path(test_patch_path)
            if actual_test_patch_sha != instance.official_test_patch_sha256:
                issues.append(f"{instance.instance_id} test patch fixture sha256 mismatch")

        prediction = prediction_lookup.get(instance.instance_id)
        if prediction is None:
            issues.append(f"{instance.instance_id} missing from sample predictions")
        else:
            expected_prediction_fields = set(bundle.judge_config.official_evaluator.required_prediction_fields)
            if set(prediction) != expected_prediction_fields:
                issues.append(f"{instance.instance_id} prediction fields do not match judge config")
            if prediction.get("model_name_or_path") != "gold":
                issues.append(f"{instance.instance_id} sample prediction must use the gold label")
            if hashlib.sha256(prediction.get("model_patch", "").encode("utf-8")).hexdigest() != instance.official_patch_sha256:
                issues.append(f"{instance.instance_id} sample prediction patch does not match fixture sha256")

    _require_keys(bundle.export_golden, bundle.export_contract.top_level_required, label="export_golden", issues=issues)

    export_instances = bundle.export_golden.get("instances", [])
    if [row.get("instance_id") for row in export_instances] != instance_ids:
        issues.append("export_golden instances do not match manifest order")

    for row in export_instances:
        instance_id = row.get("instance_id", "<missing>")
        _require_keys(row, bundle.export_contract.instance_required, label=f"export_golden[{instance_id}]", issues=issues)
        _require_keys(
            row.get("prediction_record", {}),
            bundle.export_contract.prediction_record_required,
            label=f"export_golden[{instance_id}].prediction_record",
            issues=issues,
        )
        _require_keys(
            row.get("judge_inputs", {}),
            bundle.export_contract.judge_inputs_required,
            label=f"export_golden[{instance_id}].judge_inputs",
            issues=issues,
        )
        _require_keys(
            row.get("judge_result", {}),
            bundle.export_contract.judge_result_required,
            label=f"export_golden[{instance_id}].judge_result",
            issues=issues,
        )
        _require_keys(
            row.get("artifacts", {}),
            bundle.export_contract.artifacts_required,
            label=f"export_golden[{instance_id}].artifacts",
            issues=issues,
        )

    judge_request = bundle.rpc["judge_request"]
    judge_response = bundle.rpc["judge_response"]
    export_request = bundle.rpc["export_request"]
    export_response = bundle.rpc["export_response"]
    if judge_request.get("jsonrpc") != "2.0" or judge_response.get("jsonrpc") != "2.0":
        issues.append("judge rpc fixtures must use jsonrpc=2.0")
    if export_request.get("jsonrpc") != "2.0" or export_response.get("jsonrpc") != "2.0":
        issues.append("export rpc fixtures must use jsonrpc=2.0")
    if judge_request.get("id") != judge_response.get("id"):
        issues.append("judge rpc request/response ids do not match")
    if export_request.get("id") != export_response.get("id"):
        issues.append("export rpc request/response ids do not match")
    for rpc_key, payload_key in (
        ("judge_request", "judge_config_path"),
        ("judge_request", "evaluator_input_path"),
        ("export_request", "contract_path"),
        ("export_request", "source_slice_path"),
    ):
        target = bundle.rpc[rpc_key]["params"][payload_key]
        if not resolve_repo_path(target).exists():
            issues.append(f"{rpc_key} references a missing file: {target}")

    return issues


def validate_official_dataset_alignment(bundle: SmokeAssetBundle, dataset_rows: list[dict[str, Any]] | None = None) -> list[str]:
    if dataset_rows is None:
        from datasets import load_dataset

        dataset_rows = list(
            load_dataset(
                bundle.manifest.benchmark.dataset_name,
                split=bundle.manifest.benchmark.dataset_split,
            )
        )

    row_lookup = {row["instance_id"]: row for row in dataset_rows}
    issues: list[str] = []
    for instance in bundle.manifest.instances:
        row = row_lookup.get(instance.instance_id)
        if row is None:
            issues.append(f"{instance.instance_id} is missing from the official dataset")
            continue
        if row["repo"] != instance.repo:
            issues.append(f"{instance.instance_id} repo does not match official dataset")
        if row["base_commit"] != instance.base_commit:
            issues.append(f"{instance.instance_id} base_commit does not match official dataset")
        if row["environment_setup_commit"] != instance.environment_setup_commit:
            issues.append(f"{instance.instance_id} environment_setup_commit does not match official dataset")
        if row["difficulty"] != instance.difficulty:
            issues.append(f"{instance.instance_id} difficulty does not match official dataset")
        if row["problem_statement"] != instance.problem_statement:
            issues.append(f"{instance.instance_id} problem_statement does not match official dataset")
        if row.get("hints_text", "") != instance.hints_text:
            issues.append(f"{instance.instance_id} hints_text does not match official dataset")
        fail_to_pass = json.loads(row["FAIL_TO_PASS"])
        pass_to_pass = json.loads(row["PASS_TO_PASS"])
        if fail_to_pass != instance.fail_to_pass:
            issues.append(f"{instance.instance_id} FAIL_TO_PASS does not match official dataset")
        if pass_to_pass != instance.pass_to_pass:
            issues.append(f"{instance.instance_id} PASS_TO_PASS does not match official dataset")
        if hashlib.sha256(row["patch"].encode("utf-8")).hexdigest() != instance.official_patch_sha256:
            issues.append(f"{instance.instance_id} patch sha256 does not match official dataset")
        if hashlib.sha256(row["test_patch"].encode("utf-8")).hexdigest() != instance.official_test_patch_sha256:
            issues.append(f"{instance.instance_id} test_patch sha256 does not match official dataset")
    return issues
