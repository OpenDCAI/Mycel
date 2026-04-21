# SWE-bench Verified Smoke Slice

This directory freezes the `#13` P0 sample assets for a `SWE-bench Verified` smoke slice. It does not add judge or export platform code; it fixes the sample inputs that `#12` and `#14` will consume later.

## Data source

- Dataset: `SWE-bench/SWE-bench_Verified`
- Dataset split: `test`
- Dataset revision: `91aa3ed51b709be6457e12d00300a6a596d4c6a3`
- Official dataset guide: `https://www.swebench.com/SWE-bench/guides/datasets/`
- Official evaluation guide: `https://www.swebench.com/SWE-bench/guides/evaluation/`
- Official repo: `https://github.com/SWE-bench/SWE-bench`

## Slice rules

- Single repo only: `pytest-dev/pytest`
- Single `environment_setup_commit` only: `634cde9506eb1f48dec3ec77974ee8dc952207c6`
- Three verified instances:
  - `pytest-dev__pytest-7521`
  - `pytest-dev__pytest-7571`
  - `pytest-dev__pytest-7490`
- Selection bias:
  - prefer `<15 min fix` or `15 min - 1 hour`
  - prefer `1-2` `FAIL_TO_PASS` tests
  - keep one repo + one env pin so smoke prep can reuse a single checkout and environment

## Files

- `smoke/manifest.json`: frozen instance definitions with `repo`, `base_commit`, test mappings, and official patch hashes
- `smoke/judge_config.json`: P0 judge profile and official evaluator invocation template
- `smoke/sample_evaluator_input.json`: concrete evaluator input envelope for the smoke slice
- `smoke/sample_predictions.jsonl`: gold-format prediction records using the official dataset patches
- `smoke/export_contract.json`: minimum backend export fields that `#12` must align with
- `smoke/export_golden.json`: golden export fixture for contract verification
- `smoke/rpc/*.json`: JSON-RPC request/response fixtures that simulate judge/export preparation calls
- `smoke/fixtures/official_patches/*`: official solution patches and test patches pinned by sha256

## Validation entrypoints

- Static asset + branch coverage under the project Python 3.12 environment:
  - `./.venv/bin/python3.12 -m pytest tests/Unit/eval/test_swe_verified_assets.py`
- Smoke asset verification without the optional `datasets` dependency:
  - `./.venv/bin/python3.12 -m eval.benchmarks.swe_verified.verify_smoke_assets --skip-official-dataset`
- Full alignment against the upstream dataset in an environment where `datasets` is installed:
  - `python -m eval.benchmarks.swe_verified.verify_smoke_assets`

## Current boundary

- Completed here:
  - sample instances
  - repo / commit pins
  - judge config
  - evaluator input assets
  - export contract and golden fixture
  - JSON-RPC preparation fixtures
- Still blocked on `#12`:
  - no benchmark-aware judge bridge in product code
  - no backend export API that emits the contract shape
  - no repo checkout / evaluator orchestration wired into monitor batches
- Once `#12` is ready:
  - feed `smoke/sample_evaluator_input.json` into the new judge bridge
  - emit an export payload and diff it against `smoke/export_golden.json`
  - use `smoke/rpc/*.json` as request/response contract fixtures for backend tests
