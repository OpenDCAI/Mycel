# SWE-bench Nightly Dashboard (Heartbeat Progress)

- Generated (UTC): `2026-02-24T16:08:14.772092+00:00`
- Scope: heartbeat-driven small-slice swebench progression

## KPI Table
| run_id | profile | recursion_limit | n | non_empty_patch | errors | invalid_tool_bash | recursion_limit_errors | avg_checkpoints | avg_tool_calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| case003-a | baseline | 24 | 3 | 0 | 3 | 0 | 3 | 26.0 | 9.0 |
| case003-b | heuristic | 24 | 3 | 0 | 3 | 0 | 3 | 26.0 | 8.3 |
| case004-b | heuristic | 40 | 3 | 0 | 3 | 0 | 3 | 42.0 | 14.7 |
| case005-a | baseline | 80 | 5 | 5 | 0 | 0 | 0 | 51.0 | 16.4 |
| case005-b | heuristic | 80 | 5 | 5 | 0 | 0 | 0 | 56.4 | 18.0 |

## Visuals
![Patch vs Errors](nightly-20260224-patch-errors.svg)

![Search Cost](nightly-20260224-cost.svg)

## Linked Artifacts
- `case003-a`: `/home/ubuntu/share/log/eval/2026-02-24-prev-results/swebench_runs/case003-a`
- `case003-b`: `/home/ubuntu/share/log/eval/2026-02-24-prev-results/swebench_runs/case003-b`
- `case004-b`: `/home/ubuntu/share/log/eval/2026-02-24-prev-results/swebench_runs/case004-b`
- `case005-a`: `/home/ubuntu/share/log/eval/2026-02-24-prev-results/swebench_runs/case005-a`
- `case005-b`: `/home/ubuntu/share/log/eval/2026-02-24-prev-results/swebench_runs/case005-b`
- case report: `/home/ubuntu/share/log/eval/latest/case_reports/case003-prompt-ab.md`
- case report: `/home/ubuntu/share/log/eval/latest/case_reports/case005-prompt-ab.md`

## Takeaways
1. `recursion_limit=24/40` produced hard ceiling failures; `recursion_limit=80` unlocked consistent non-empty patches on sampled set.
2. For this sampled band, prompt-profile changes mainly shifted search cost, not patch production rate.
3. `invalid_tool_bash` remained zero in recent runs; current bottleneck moved from tool-name mismatch to search/exploration budget.
