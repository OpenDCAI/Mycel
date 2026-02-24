# Case-Driven A/B Workflow for SWE-bench

目标：用小步 A/B 对照把 `leonai` 跑顺，并把证据直接绑定到 PR，避免退化。

## 1) 跑 A 组（基线）

```bash
set -a; source ~/.leon/.env; set +a
uv run python3 eval/swebench/run_slice.py \
  --run-id ab-a-001 \
  --arm A \
  --prompt-profile baseline \
  --dataset SWE-bench/SWE-bench_Lite \
  --split test \
  --start 0 \
  --count 1 \
  --timeout-sec 240 \
  --recursion-limit 24 \
  --no-eval
```

## 2) 跑 B 组（启发式）

严格 A/B：每轮只改一个变量。下面示例只改 `prompt_profile`，其余保持和 A 一致。

```bash
set -a; source ~/.leon/.env; set +a
uv run python3 eval/swebench/run_slice.py \
  --run-id ab-b-001 \
  --arm B \
  --prompt-profile heuristic \
  --dataset SWE-bench/SWE-bench_Lite \
  --split test \
  --start 0 \
  --count 1 \
  --timeout-sec 240 \
  --recursion-limit 24 \
  --no-eval
```

## 3) 生成 self-contained 案例报告

```bash
uv run python3 eval/swebench/build_case_report.py \
  --run-a artifacts/swebench/ab-a-001 \
  --run-b artifacts/swebench/ab-b-001 \
  --title "LeonAI SWE-bench Case-001"
```

输出：
- `artifacts/swebench/ab-b-001/case_report_ab.md`
- `artifacts/swebench/ab-b-001/case_report_ab.json`

## 4) PR 最小准入

1. 报告里 `patch_non_empty` 不下降。  
2. `invalid_tool_bash` 不上升。  
3. 关键错误（如 recursion_limit）有解释，并给出下一轮假设。  
4. 报告中 `A/B 变量纯度检查` 必须是 `clean`；若为 `confounded`，只能作为探索性证据。  
