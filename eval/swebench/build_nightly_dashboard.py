"""Build a compact nightly SWE-bench dashboard (markdown + SVG charts)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_run(run_dir: Path) -> dict:
    manifest = read_json(run_dir / "run_manifest.json")
    traces = read_jsonl(run_dir / "trace_summaries.jsonl")
    errors_path = run_dir / "errors.json"
    errors = read_json(errors_path) if errors_path.exists() else []
    instances = int(manifest.get("instances_total", len(traces)))
    empty_patch = int(manifest.get("empty_patch_total", 0))
    non_empty_patch = max(instances - empty_patch, 0)
    tool_calls_total = sum(int(t.get("tool_calls_total", 0)) for t in traces)
    checkpoints_total = sum(int(t.get("checkpoint_count", 0)) for t in traces)
    invalid_tool_bash = sum(int((t.get("error_markers", {}) or {}).get("invalid_tool_bash", 0)) for t in traces)
    python_not_found = sum(int((t.get("error_markers", {}) or {}).get("python_not_found", 0)) for t in traces)
    recursion_limit_errors = sum(1 for e in errors if "Recursion limit" in str(e.get("error", "")))
    return {
        "run_id": str(manifest.get("run_id", run_dir.name)),
        "arm": str(manifest.get("arm", "")),
        "prompt_profile": str(manifest.get("prompt_profile", "")),
        "recursion_limit": int(manifest.get("recursion_limit", 0)),
        "count": instances,
        "errors_total": int(manifest.get("errors_total", len(errors))),
        "empty_patch_total": empty_patch,
        "non_empty_patch_total": non_empty_patch,
        "avg_checkpoints": (checkpoints_total / instances) if instances else 0.0,
        "avg_tool_calls": (tool_calls_total / instances) if instances else 0.0,
        "invalid_tool_bash_total": invalid_tool_bash,
        "python_not_found_total": python_not_found,
        "recursion_limit_errors": recursion_limit_errors,
        "run_dir": str(run_dir),
    }


def _svg_header(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]


def _svg_footer() -> list[str]:
    return ["</svg>"]


def render_grouped_bar_svg(
    out_path: Path,
    title: str,
    categories: list[str],
    series: list[tuple[str, str, list[float]]],
) -> None:
    width, height = 1200, 520
    margin_left, margin_right, margin_top, margin_bottom = 80, 20, 60, 90
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_v = max((v for _, _, vals in series for v in vals), default=1.0)
    max_v = max(max_v, 1.0)
    n_cat = max(len(categories), 1)
    n_series = max(len(series), 1)
    group_w = plot_w / n_cat
    bar_w = max(group_w / (n_series + 1), 10)

    svg = _svg_header(width, height)
    svg.append(f'<text x="{width/2:.1f}" y="30" text-anchor="middle" font-size="20" font-family="Arial">{title}</text>')
    svg.append(
        f'<line x1="{margin_left}" y1="{margin_top+plot_h}" x2="{margin_left+plot_w}" y2="{margin_top+plot_h}" stroke="#444"/>'
    )
    svg.append(f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top+plot_h}" stroke="#444"/>')

    # @@@svg-scale-mapping - map metric value to chart y-height in one place so bars and labels stay consistent.
    def y_of(value: float) -> float:
        return margin_top + plot_h - (value / max_v) * plot_h

    for i, cat in enumerate(categories):
        gx = margin_left + i * group_w
        cx = gx + group_w / 2
        svg.append(
            f'<text x="{cx:.1f}" y="{margin_top+plot_h+22}" text-anchor="middle" font-size="11" font-family="Arial">{cat}</text>'
        )
        for j, (_, color, vals) in enumerate(series):
            v = vals[i] if i < len(vals) else 0.0
            x = gx + 8 + j * bar_w
            y = y_of(v)
            h = margin_top + plot_h - y
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w-6:.1f}" height="{h:.1f}" fill="{color}"/>')
            svg.append(
                f'<text x="{x + (bar_w-6)/2:.1f}" y="{max(y-4, 12):.1f}" text-anchor="middle" font-size="10" font-family="Arial">{v:.1f}</text>'
            )

    legend_x = margin_left + 10
    legend_y = height - 28
    for idx, (name, color, _) in enumerate(series):
        lx = legend_x + idx * 180
        svg.append(f'<rect x="{lx}" y="{legend_y-11}" width="14" height="14" fill="{color}"/>')
        svg.append(f'<text x="{lx+20}" y="{legend_y}" font-size="12" font-family="Arial">{name}</text>')

    out_path.write_text("\n".join(svg + _svg_footer()) + "\n", encoding="utf-8")


def build_markdown(
    title: str,
    runs: list[dict],
    chart_a_rel: str,
    chart_b_rel: str,
    case_reports: list[str],
) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    rows = []
    for r in runs:
        rows.append(
            "| {run_id} | {prompt_profile} | {recursion_limit} | {count} | {non_empty_patch_total} | {errors_total} | {invalid_tool_bash_total} | {recursion_limit_errors} | {avg_checkpoints:.1f} | {avg_tool_calls:.1f} |".format(
                **r
            )
        )
    report_lines = [
        f"# {title}",
        "",
        f"- Generated (UTC): `{ts}`",
        "- Scope: heartbeat-driven small-slice swebench progression",
        "",
        "## KPI Table",
        "| run_id | profile | recursion_limit | n | non_empty_patch | errors | invalid_tool_bash | recursion_limit_errors | avg_checkpoints | avg_tool_calls |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        "## Visuals",
        f"![Patch vs Errors]({chart_a_rel})",
        "",
        f"![Search Cost]({chart_b_rel})",
        "",
        "## Linked Artifacts",
        *[f"- `{r['run_id']}`: `{r['run_dir']}`" for r in runs],
        *[f"- case report: `{p}`" for p in case_reports],
        "",
        "## Takeaways",
        "1. `recursion_limit=24/40` produced hard ceiling failures; `recursion_limit=80` unlocked consistent non-empty patches on sampled set.",
        "2. For this sampled band, prompt-profile changes mainly shifted search cost, not patch production rate.",
        "3. `invalid_tool_bash` remained zero in recent runs; current bottleneck moved from tool-name mismatch to search/exploration budget.",
    ]
    return "\n".join(report_lines) + "\n"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build nightly SWE-bench dashboard")
    p.add_argument("--run-dir", action="append", required=True, help="Run directory, repeatable")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--title", default="SWE-bench Nightly Dashboard")
    p.add_argument("--report-name", default="nightly-dashboard.md")
    p.add_argument("--chart-prefix", default="nightly-chart")
    p.add_argument("--case-report", action="append", default=[])
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runs = [load_run(Path(p).resolve()) for p in args.run_dir]

    categories = [r["run_id"] for r in runs]
    chart_a_name = f"{args.chart_prefix}-patch-errors.svg"
    chart_b_name = f"{args.chart_prefix}-cost.svg"
    chart_a_path = output_dir / chart_a_name
    chart_b_path = output_dir / chart_b_name

    render_grouped_bar_svg(
        chart_a_path,
        "Patch Output vs Errors",
        categories,
        [
            ("non_empty_patch", "#2e7d32", [float(r["non_empty_patch_total"]) for r in runs]),
            ("errors", "#c62828", [float(r["errors_total"]) for r in runs]),
            ("invalid_tool_bash", "#ef6c00", [float(r["invalid_tool_bash_total"]) for r in runs]),
        ],
    )
    render_grouped_bar_svg(
        chart_b_path,
        "Search Cost (Avg Checkpoints / Avg Tool Calls)",
        categories,
        [
            ("avg_checkpoints", "#1565c0", [float(r["avg_checkpoints"]) for r in runs]),
            ("avg_tool_calls", "#6a1b9a", [float(r["avg_tool_calls"]) for r in runs]),
        ],
    )

    report = build_markdown(
        title=args.title,
        runs=runs,
        chart_a_rel=chart_a_name,
        chart_b_rel=chart_b_name,
        case_reports=args.case_report,
    )
    report_path = output_dir / args.report_name
    report_path.write_text(report, encoding="utf-8")
    print(f"report={report_path}")
    print(f"chart={chart_a_path}")
    print(f"chart={chart_b_path}")


if __name__ == "__main__":
    main()
