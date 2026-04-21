import { describe, expect, it } from "vitest";

import {
  buildCompareMetricRows,
  buildLeaderboardRows,
  buildScenarioFacetOptions,
  filterScenariosByBenchmark,
  resolveBatchExportFormat,
  summarizeSelectedScenarioContracts,
  type EvaluationBatchListItem,
  type EvaluationScenarioCatalogItem,
  type EvaluationScenarioRef,
} from "./evaluation-model";

const benchmarkScenarios: EvaluationScenarioCatalogItem[] = [
  {
    scenario_id: "swe-1",
    benchmark: {
      family: "SWE-bench Verified",
      instance_id: "pytest-dev__pytest-7521",
    },
    judge_type: "swe_verified_smoke",
    export_format: "predictions_jsonl",
    workspace: {
      repo: "pytest-dev/pytest",
      base_commit: "abc123",
    },
  },
  {
    scenario_id: "swe-2",
    benchmark: {
      family: "SWE-bench Verified",
      instance_id: "pytest-dev__pytest-7571",
    },
    judge_type: "swe_verified_smoke",
    export_format: "predictions_jsonl",
    workspace: {
      repo: "pytest-dev/pytest",
      base_commit: "def456",
    },
  },
  {
    scenario_id: "terminal-1",
    benchmark: {
      family: "Terminal-Bench",
      instance_id: "terminal-001",
    },
    judge_type: "terminal_smoke",
    export_format: "generic_json",
  },
  {
    scenario_id: "legacy-scenario",
    judge_type: null,
    export_format: null,
    benchmark: null,
  },
];

describe("evaluation model helpers", () => {
  it("builds benchmark facet options from the live scenario surface", () => {
    expect(buildScenarioFacetOptions(benchmarkScenarios, "SWE-bench Verified")).toEqual({
      benchmarkScenarioCount: 3,
      families: ["SWE-bench Verified", "Terminal-Bench"],
      instanceIds: ["pytest-dev__pytest-7521", "pytest-dev__pytest-7571"],
      judgeTypes: ["swe_verified_smoke"],
      exportFormats: ["predictions_jsonl"],
    });
  });

  it("filters scenarios only by benchmark fields that are actually selected", () => {
    const result = filterScenariosByBenchmark(benchmarkScenarios, {
      family: "SWE-bench Verified",
      instanceId: "",
      judgeType: "swe_verified_smoke",
      exportFormat: "predictions_jsonl",
    });

    expect(result.map((item) => item.scenario_id)).toEqual(["swe-1", "swe-2"]);
  });

  it("summarizes selected scenario contracts without hiding missing metadata", () => {
    expect(summarizeSelectedScenarioContracts(benchmarkScenarios)).toEqual({
      totalCount: 4,
      missingBenchmarkMetadataCount: 1,
      families: ["SWE-bench Verified", "Terminal-Bench"],
      instances: ["pytest-dev__pytest-7521", "pytest-dev__pytest-7571", "terminal-001"],
      judgeTypes: ["swe_verified_smoke", "terminal_smoke"],
      exportFormats: ["generic_json", "predictions_jsonl"],
      repos: ["pytest-dev/pytest"],
      baseCommits: ["abc123", "def456"],
    });
  });

  it("orders leaderboard rows by pass rate first and recency second", () => {
    const rows = buildLeaderboardRows([
      {
        batch_id: "older-high",
        created_at: "2026-04-18T10:00:00Z",
        summary_json: { pass_rate: 1, total_runs: 2, judge_passed_runs: 2 },
      },
      {
        batch_id: "newer-low",
        created_at: "2026-04-20T10:00:00Z",
        summary_json: { pass_rate: 0.5, total_runs: 2, judge_passed_runs: 1 },
      },
      {
        batch_id: "newer-high",
        created_at: "2026-04-21T10:00:00Z",
        summary_json: { pass_rate: 1, total_runs: 3, judge_passed_runs: 3 },
      },
    ] satisfies EvaluationBatchListItem[]);

    expect(rows.map((row) => row.batchId)).toEqual(["newer-high", "older-high", "newer-low"]);
  });

  it("resolves export format from scenario refs and falls back when missing", () => {
    expect(
      resolveBatchExportFormat([
        { export: { format: "predictions_jsonl" } },
        { export: { format: "generic_json" } },
      ] satisfies EvaluationScenarioRef[]),
    ).toBe("generic_json");

    expect(resolveBatchExportFormat([])).toBe("generic_json");
  });

  it("marks comparison regressions when pass rate drops or judge failures rise", () => {
    const rows = buildCompareMetricRows({
      delta: {
        pass_rate: { baseline: 1, candidate: 0.5, delta: -0.5 },
        judge_passed_runs: { baseline: 3, candidate: 2, delta: -1 },
        judge_failed_runs: { baseline: 0, candidate: 1, delta: 1 },
        avg_total_tokens: { baseline: 100, candidate: 120, delta: 20 },
        artifact_count_total: { baseline: 4, candidate: 5, delta: 1 },
        avg_scores: {
          resolved: { baseline: 1, candidate: 0, delta: -1 },
        },
      },
    });

    expect(rows.filter((row) => row.regression).map((row) => row.key)).toEqual([
      "pass_rate",
      "judge_passed_runs",
      "judge_failed_runs",
      "avg_scores.resolved",
    ]);
  });
});
