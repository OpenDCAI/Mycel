"""Build a self-contained A/B case report from SWE-bench run artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


AB_VARIABLES = ("recursion_limit", "timeout_sec", "prompt_profile")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def is_recursion_limit_error(text: str) -> bool:
    return "recursion limit of" in text.lower()


def compare_ab_variables(cfg_a: dict[str, Any], cfg_b: dict[str, Any]) -> dict[str, Any]:
    # @@@ab-purity-rule - strict A/B attribution needs exactly one changed variable; otherwise mark as confounded.
    changed_variables = [k for k in AB_VARIABLES if cfg_a.get(k) != cfg_b.get(k)]
    return {
        "ab_variables": list(AB_VARIABLES),
        "changed_variables": changed_variables,
        "is_confounded": len(changed_variables) > 1,
    }


def load_run(run_dir: Path) -> dict[str, Any]:
    manifest = read_json(run_dir / "run_manifest.json")
    predictions = read_jsonl(run_dir / "predictions.jsonl")
    traces = read_jsonl(run_dir / "trace_summaries.jsonl")
    errors_path = run_dir / "errors.json"
    errors = read_json(errors_path) if errors_path.exists() else []

    pred_by_id = {p["instance_id"]: p for p in predictions}
    trace_by_id = {t["instance_id"]: t for t in traces}
    err_by_id = {e["instance_id"]: e.get("error", "") for e in errors}

    patch_non_empty = sum(1 for p in predictions if p.get("model_patch", "").strip())
    invalid_tool_bash = sum(int(t.get("error_markers", {}).get("invalid_tool_bash", 0)) for t in traces)
    # @@@recursion-hit-definition - count only terminal errors to keep one clear metric source.
    recursion_hits = sum(1 for e in errors if is_recursion_limit_error(str(e.get("error", ""))))
    avg_checkpoints = mean([int(t.get("checkpoint_count", 0)) for t in traces]) if traces else 0.0
    avg_tool_calls = mean([int(t.get("tool_calls_total", 0)) for t in traces]) if traces else 0.0

    return {
        "manifest": manifest,
        "predictions": predictions,
        "traces": traces,
        "errors": errors,
        "pred_by_id": pred_by_id,
        "trace_by_id": trace_by_id,
        "err_by_id": err_by_id,
        "metrics": {
            "instances": len(predictions),
            "patch_non_empty": patch_non_empty,
            "patch_empty": len(predictions) - patch_non_empty,
            "errors": len(errors),
            "invalid_tool_bash": invalid_tool_bash,
            "recursion_limit_hits": recursion_hits,
            "avg_checkpoints": avg_checkpoints,
            "avg_tool_calls": avg_tool_calls,
        },
    }


def pick_case_id(run_a: dict[str, Any], run_b: dict[str, Any]) -> str:
    ids = sorted(set(run_a["pred_by_id"]).intersection(run_b["pred_by_id"]))
    if not ids:
        raise RuntimeError("no overlapping instance ids between run A and run B")
    return ids[0]


def summarize_case(case_id: str, run_data: dict[str, Any]) -> dict[str, Any]:
    pred = run_data["pred_by_id"].get(case_id, {})
    trace = run_data["trace_by_id"].get(case_id, {})
    err = run_data["err_by_id"].get(case_id, "")
    return {
        "instance_id": case_id,
        "patch_len": len(pred.get("model_patch", "")),
        "checkpoint_count": int(trace.get("checkpoint_count", 0)),
        "tool_calls_total": int(trace.get("tool_calls_total", 0)),
        "invalid_tool_bash": int(trace.get("error_markers", {}).get("invalid_tool_bash", 0)),
        "recursion_limit": int(trace.get("error_markers", {}).get("recursion_limit", 0)),
        "error": err,
        "last_ai_message": trace.get("last_ai_message", ""),
    }


def infer_conclusion(metrics_a: dict[str, Any], metrics_b: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if metrics_b["patch_non_empty"] > metrics_a["patch_non_empty"]:
        lines.append("B 的非空 patch 数提升，说明改动提高了收敛概率。")
    elif metrics_b["patch_non_empty"] < metrics_a["patch_non_empty"]:
        lines.append("B 的非空 patch 数下降，说明改动可能有退化。")
    else:
        lines.append("A/B 的非空 patch 数持平。")

    if metrics_b["invalid_tool_bash"] < metrics_a["invalid_tool_bash"]:
        lines.append("B 显著减少了 `bash` 非法工具调用，工具协议对齐更好。")
    if metrics_b["recursion_limit_hits"] < metrics_a["recursion_limit_hits"]:
        lines.append("B 的 recursion limit 命中下降，停止条件更接近可收敛状态。")
    if metrics_b["avg_checkpoints"] > metrics_a["avg_checkpoints"]:
        lines.append("B 平均 checkpoint 更高，探索更充分，但要警惕成本上升。")
    return lines


def build_markdown(
    title: str,
    case_id: str,
    run_a: dict[str, Any],
    run_b: dict[str, Any],
    case_a: dict[str, Any],
    case_b: dict[str, Any],
    ab_diff: dict[str, Any],
) -> str:
    ma = run_a["metrics"]
    mb = run_b["metrics"]
    cfg_a = run_a["manifest"]
    cfg_b = run_b["manifest"]

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- 生成时间(UTC): {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- 数据集: `{cfg_a['dataset']}` / split `{cfg_a['split']}`")
    lines.append(f"- 对照组 A: run_id=`{cfg_a['run_id']}` arm=`{cfg_a['arm']}` profile=`{cfg_a['prompt_profile']}`")
    lines.append(f"- 实验组 B: run_id=`{cfg_b['run_id']}` arm=`{cfg_b['arm']}` profile=`{cfg_b['prompt_profile']}`")
    lines.append("")
    lines.append("## 背景与目标")
    lines.append("目标是通过小步 A/B 对照，验证启发式改动是否提高 SWE-bench 任务收敛性，同时避免退化。")
    lines.append("")
    lines.append("## 配置对照")
    lines.append("| 维度 | A | B |")
    lines.append("|---|---|---|")
    lines.append(f"| recursion_limit | {cfg_a['recursion_limit']} | {cfg_b['recursion_limit']} |")
    lines.append(f"| timeout_sec | {cfg_a['timeout_sec']} | {cfg_b['timeout_sec']} |")
    lines.append(f"| prompt_profile | {cfg_a['prompt_profile']} | {cfg_b['prompt_profile']} |")
    lines.append("")
    lines.append("## A/B 变量纯度检查")
    lines.append(f"- 对照变量: `{', '.join(ab_diff['ab_variables'])}`")
    lines.append(f"- 本轮变化变量: `{', '.join(ab_diff['changed_variables']) or '(none)'}`")
    if ab_diff["is_confounded"]:
        lines.append("- 结论: `confounded`（本轮变化变量 > 1，不满足严格因果归因）")
    else:
        lines.append("- 结论: `clean`（本轮只改变 1 个变量，可做严格归因）")
    lines.append("")
    lines.append("## 总体指标")
    lines.append("| 指标 | A | B |")
    lines.append("|---|---:|---:|")
    lines.append(f"| instances | {ma['instances']} | {mb['instances']} |")
    lines.append(f"| patch_non_empty | {ma['patch_non_empty']} | {mb['patch_non_empty']} |")
    lines.append(f"| patch_empty | {ma['patch_empty']} | {mb['patch_empty']} |")
    lines.append(f"| errors | {ma['errors']} | {mb['errors']} |")
    lines.append(f"| invalid_tool_bash | {ma['invalid_tool_bash']} | {mb['invalid_tool_bash']} |")
    lines.append(f"| recursion_limit_hits | {ma['recursion_limit_hits']} | {mb['recursion_limit_hits']} |")
    lines.append(f"| avg_checkpoints | {ma['avg_checkpoints']:.2f} | {mb['avg_checkpoints']:.2f} |")
    lines.append(f"| avg_tool_calls | {ma['avg_tool_calls']:.2f} | {mb['avg_tool_calls']:.2f} |")
    lines.append("")
    lines.append(f"## 单案例详解: `{case_id}`")
    lines.append("| 字段 | A | B |")
    lines.append("|---|---|---|")
    lines.append(f"| patch_len | {case_a['patch_len']} | {case_b['patch_len']} |")
    lines.append(f"| checkpoint_count | {case_a['checkpoint_count']} | {case_b['checkpoint_count']} |")
    lines.append(f"| tool_calls_total | {case_a['tool_calls_total']} | {case_b['tool_calls_total']} |")
    lines.append(f"| invalid_tool_bash | {case_a['invalid_tool_bash']} | {case_b['invalid_tool_bash']} |")
    lines.append(f"| recursion_limit | {case_a['recursion_limit']} | {case_b['recursion_limit']} |")
    lines.append("")
    lines.append("A 最后错误:")
    lines.append(f"- `{case_a['error'] or 'N/A'}`")
    lines.append("B 最后错误:")
    lines.append(f"- `{case_b['error'] or 'N/A'}`")
    lines.append("")
    lines.append("## 归因结论")
    for line in infer_conclusion(ma, mb):
        lines.append(f"- {line}")
    lines.append("")
    lines.append("## 关联代码改动")
    lines.append("- `eval/swebench/run_slice.py`")
    lines.append("- `eval/swebench/build_case_report.py`")
    lines.append("")
    lines.append("## 下一步")
    lines.append("1. 保持每次只改一类启发式，并固定 1~5 条小样本做 A/B。")
    lines.append("2. 每轮都产出本报告，作为 PR 的证据附件。")
    lines.append("3. 指标稳定后再扩大样本，避免回归不可见。")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build a self-contained A/B case report")
    p.add_argument("--run-a", required=True, help="Run A directory")
    p.add_argument("--run-b", required=True, help="Run B directory")
    p.add_argument("--title", default="LeonAI SWE-bench A/B Case Report")
    p.add_argument("--output", default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    run_a_dir = Path(args.run_a).expanduser().resolve()
    run_b_dir = Path(args.run_b).expanduser().resolve()
    run_a = load_run(run_a_dir)
    run_b = load_run(run_b_dir)
    ab_diff = compare_ab_variables(run_a["manifest"], run_b["manifest"])

    case_id = pick_case_id(run_a, run_b)
    case_a = summarize_case(case_id, run_a)
    case_b = summarize_case(case_id, run_b)
    report = build_markdown(args.title, case_id, run_a, run_b, case_a, case_b, ab_diff)

    output_path = Path(args.output).expanduser().resolve() if args.output else run_b_dir / "case_report_ab.md"
    output_path.write_text(report, encoding="utf-8")

    json_path = output_path.with_suffix(".json")
    # @@@report-json-payload - keep a machine-readable mirror so follow-up PR checks can diff metrics directly.
    json_path.write_text(
        json.dumps(
            {
                "title": args.title,
                "case_id": case_id,
                "run_a_dir": str(run_a_dir),
                "run_b_dir": str(run_b_dir),
                "metrics_a": run_a["metrics"],
                "metrics_b": run_b["metrics"],
                "ab_diff": ab_diff,
                "case_a": case_a,
                "case_b": case_b,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"report_md={output_path}")
    print(f"report_json={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
