# LeonAI SWE-bench Case-001 (A/B)

- 生成时间(UTC): 2026-02-24T07:09:52.389369+00:00
- 数据集: `SWE-bench/SWE-bench_Lite` / split `test`
- 对照组 A: run_id=`case001-a` arm=`A` profile=`baseline`
- 实验组 B: run_id=`case001-b` arm=`B` profile=`heuristic`

## 背景与目标
目标是通过小步 A/B 对照，验证启发式改动是否提高 SWE-bench 任务收敛性，同时避免退化。

## 配置对照
| 维度 | A | B |
|---|---|---|
| recursion_limit | 24 | 40 |
| timeout_sec | 240 | 240 |
| prompt_profile | baseline | heuristic |

## A/B 变量纯度检查
- 对照变量: `recursion_limit, timeout_sec, prompt_profile`
- 本轮变化变量: `recursion_limit, prompt_profile`
- 结论: `confounded`（本轮变化变量 > 1，不满足严格因果归因）

## 总体指标
| 指标 | A | B |
|---|---:|---:|
| instances | 1 | 1 |
| patch_non_empty | 0 | 0 |
| patch_empty | 1 | 1 |
| errors | 1 | 1 |
| invalid_tool_bash | 1 | 1 |
| recursion_limit_hits | 1 | 1 |
| avg_checkpoints | 26.00 | 42.00 |
| avg_tool_calls | 8.00 | 13.00 |

## 单案例详解: `astropy__astropy-12907`
| 字段 | A | B |
|---|---|---|
| patch_len | 0 | 0 |
| checkpoint_count | 26 | 42 |
| tool_calls_total | 8 | 13 |
| invalid_tool_bash | 1 | 1 |
| recursion_limit | 0 | 0 |

A 最后错误:
- `Recursion limit of 24 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT`
B 最后错误:
- `Recursion limit of 40 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT`

## 归因结论
- A/B 的非空 patch 数持平。
- B 平均 checkpoint 更高，探索更充分，但要警惕成本上升。

## 关联代码改动
- `eval/swebench/run_slice.py`
- `eval/swebench/build_case_report.py`

## 下一步
1. 保持每次只改一类启发式，并固定 1~5 条小样本做 A/B。
2. 每轮都产出本报告，作为 PR 的证据附件。
3. 指标稳定后再扩大样本，避免回归不可见。
