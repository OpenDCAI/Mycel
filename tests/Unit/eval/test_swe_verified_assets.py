from __future__ import annotations

import json

from eval.benchmarks.swe_verified.assets import (
    clone_bundle,
    load_smoke_asset_bundle,
    resolve_repo_path,
    validate_official_dataset_alignment,
    validate_smoke_assets,
)


def _dataset_row(bundle, instance):
    return {
        "instance_id": instance.instance_id,
        "repo": instance.repo,
        "base_commit": instance.base_commit,
        "environment_setup_commit": instance.environment_setup_commit,
        "difficulty": instance.difficulty,
        "problem_statement": instance.problem_statement,
        "hints_text": instance.hints_text,
        "FAIL_TO_PASS": json.dumps(instance.fail_to_pass),
        "PASS_TO_PASS": json.dumps(instance.pass_to_pass),
        "patch": resolve_repo_path(instance.official_patch_path).read_text(encoding="utf-8"),
        "test_patch": resolve_repo_path(instance.official_test_patch_path).read_text(encoding="utf-8"),
    }


def test_swe_verified_smoke_assets_validate_cleanly() -> None:
    bundle = load_smoke_asset_bundle()

    assert validate_smoke_assets(bundle) == []


def test_swe_verified_smoke_assets_detect_prediction_mismatch() -> None:
    bundle = clone_bundle(load_smoke_asset_bundle())
    bundle.predictions[0]["instance_id"] = "wrong-instance"

    issues = validate_smoke_assets(bundle)

    assert any("sample predictions instance_ids do not match manifest order" in issue for issue in issues)


def test_swe_verified_smoke_assets_detect_missing_export_field() -> None:
    bundle = clone_bundle(load_smoke_asset_bundle())
    bundle.export_golden["instances"][0].pop("judge_result")

    issues = validate_smoke_assets(bundle)

    assert any("judge_result" in issue for issue in issues)


def test_swe_verified_smoke_assets_detect_patch_hash_drift() -> None:
    bundle = clone_bundle(load_smoke_asset_bundle())
    bundle.manifest.instances[0].official_patch_sha256 = "deadbeef"

    issues = validate_smoke_assets(bundle)

    assert any("patch fixture sha256 mismatch" in issue for issue in issues)


def test_swe_verified_smoke_assets_match_supplied_official_rows() -> None:
    bundle = load_smoke_asset_bundle()
    rows = [_dataset_row(bundle, instance) for instance in bundle.manifest.instances]

    assert validate_official_dataset_alignment(bundle, dataset_rows=rows) == []


def test_swe_verified_smoke_assets_detect_official_dataset_drift() -> None:
    bundle = load_smoke_asset_bundle()
    rows = [_dataset_row(bundle, instance) for instance in bundle.manifest.instances]
    rows[0]["base_commit"] = "0" * 40

    issues = validate_official_dataset_alignment(bundle, dataset_rows=rows)

    assert any("base_commit does not match official dataset" in issue for issue in issues)
