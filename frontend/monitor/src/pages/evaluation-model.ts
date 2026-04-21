export type BenchmarkInfo = {
  family?: string | null;
  name?: string | null;
  split?: string | null;
  variant?: string | null;
  instance_id?: string | null;
  dataset_version?: string | null;
  tags?: string[] | null;
  source_uri?: string | null;
};

export type WorkspaceInfo = {
  cwd?: string | null;
  repo?: string | null;
  base_commit?: string | null;
  env?: Record<string, string> | null;
  setup_commands?: string[] | null;
};

export type JudgeConfigInfo = {
  type?: string | null;
  config?: Record<string, unknown> | null;
};

export type ExportConfigInfo = {
  format?: string | null;
  key?: string | null;
  config?: Record<string, unknown> | null;
};

export type EvaluationScenarioCatalogItem = {
  scenario_id?: string | null;
  name?: string | null;
  category?: string | null;
  sandbox?: string | null;
  message_count?: number | null;
  timeout_seconds?: number | null;
  benchmark?: BenchmarkInfo | null;
  workspace?: WorkspaceInfo | null;
  judge_type?: string | null;
  export_format?: string | null;
};

export type EvaluationScenarioRef = {
  scenario_id?: string | null;
  name?: string | null;
  category?: string | null;
  sandbox?: string | null;
  benchmark?: BenchmarkInfo | null;
  workspace?: WorkspaceInfo | null;
  judge_config?: JudgeConfigInfo | null;
  export?: ExportConfigInfo | null;
};

export type EvaluationBatchSummary = {
  total_runs?: number | null;
  running_runs?: number | null;
  completed_runs?: number | null;
  failed_runs?: number | null;
  judge_passed_runs?: number | null;
  judge_failed_runs?: number | null;
  pass_rate?: number | null;
  avg_total_tokens?: number | null;
  artifact_count_total?: number | null;
  avg_scores?: Record<string, number> | null;
  benchmark_families?: string[] | null;
  benchmark_splits?: string[] | null;
};

export type EvaluationBatchListItem = {
  batch_id?: string | null;
  status?: string | null;
  created_at?: string | null;
  summary_json?: EvaluationBatchSummary | null;
};

export type BenchmarkFilters = {
  family: string;
  instanceId: string;
  judgeType: string;
  exportFormat: string;
};

export type ScenarioFacetOptions = {
  benchmarkScenarioCount: number;
  families: string[];
  instanceIds: string[];
  judgeTypes: string[];
  exportFormats: string[];
};

export type SelectedScenarioContractSummary = {
  totalCount: number;
  missingBenchmarkMetadataCount: number;
  families: string[];
  instances: string[];
  judgeTypes: string[];
  exportFormats: string[];
  repos: string[];
  baseCommits: string[];
};

export type LeaderboardRow = {
  batchId: string;
  createdAt: string | null;
  status: string | null;
  passRate: number | null;
  judgePassedRuns: number;
  totalRuns: number;
  families: string[];
  splits: string[];
};

export type CompareDeltaMetric = {
  baseline?: number | null;
  candidate?: number | null;
  delta?: number | null;
};

export type ComparePayload = {
  delta?: Record<string, CompareDeltaMetric | Record<string, CompareDeltaMetric> | null> | null;
};

export type CompareMetricRow = {
  key: string;
  label: string;
  baseline: number;
  candidate: number;
  delta: number;
  regression: boolean;
};

function trimText(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

function uniqueSorted(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.map(trimText).filter(Boolean))].sort((left, right) => left.localeCompare(right));
}

function isScenarioCatalogItem(
  item: EvaluationScenarioCatalogItem | EvaluationScenarioRef,
): item is EvaluationScenarioCatalogItem {
  return "judge_type" in item || "export_format" in item;
}

function getJudgeType(item: EvaluationScenarioCatalogItem | EvaluationScenarioRef): string {
  return isScenarioCatalogItem(item) ? trimText(item.judge_type) : trimText(item.judge_config?.type);
}

function getExportFormat(item: EvaluationScenarioCatalogItem | EvaluationScenarioRef): string {
  return isScenarioCatalogItem(item) ? trimText(item.export_format) : trimText(item.export?.format);
}

export function hasScenarioBenchmarkSurface(item: EvaluationScenarioCatalogItem | EvaluationScenarioRef): boolean {
  return Boolean(
    trimText(item.benchmark?.family) ||
      trimText(item.benchmark?.instance_id) ||
      getJudgeType(item) ||
      getExportFormat(item),
  );
}

export function buildScenarioFacetOptions(
  scenarios: EvaluationScenarioCatalogItem[],
  selectedFamily = "",
): ScenarioFacetOptions {
  const benchmarkScenarioCount = scenarios.filter((scenario) => hasScenarioBenchmarkSurface(scenario)).length;
  const family = trimText(selectedFamily);
  const matchingFamilyScenarios = family
    ? scenarios.filter((scenario) => trimText(scenario.benchmark?.family) === family)
    : scenarios;

  return {
    benchmarkScenarioCount,
    families: uniqueSorted(scenarios.map((scenario) => scenario.benchmark?.family)),
    instanceIds: uniqueSorted(matchingFamilyScenarios.map((scenario) => scenario.benchmark?.instance_id)),
    judgeTypes: uniqueSorted(matchingFamilyScenarios.map((scenario) => scenario.judge_type)),
    exportFormats: uniqueSorted(matchingFamilyScenarios.map((scenario) => scenario.export_format)),
  };
}

export function filterScenariosByBenchmark(
  scenarios: EvaluationScenarioCatalogItem[],
  filters: BenchmarkFilters,
): EvaluationScenarioCatalogItem[] {
  return scenarios.filter((scenario) => {
    if (filters.family && trimText(scenario.benchmark?.family) !== trimText(filters.family)) return false;
    if (filters.instanceId && trimText(scenario.benchmark?.instance_id) !== trimText(filters.instanceId)) return false;
    if (filters.judgeType && trimText(scenario.judge_type) !== trimText(filters.judgeType)) return false;
    if (filters.exportFormat && trimText(scenario.export_format) !== trimText(filters.exportFormat)) return false;
    return true;
  });
}

export function summarizeSelectedScenarioContracts(
  scenarios: Array<EvaluationScenarioCatalogItem | EvaluationScenarioRef>,
): SelectedScenarioContractSummary {
  return {
    totalCount: scenarios.length,
    missingBenchmarkMetadataCount: scenarios.filter((scenario) => !hasScenarioBenchmarkSurface(scenario)).length,
    families: uniqueSorted(scenarios.map((scenario) => scenario.benchmark?.family)),
    instances: uniqueSorted(scenarios.map((scenario) => scenario.benchmark?.instance_id)),
    judgeTypes: uniqueSorted(scenarios.map((scenario) => getJudgeType(scenario))),
    exportFormats: uniqueSorted(scenarios.map((scenario) => getExportFormat(scenario))),
    repos: uniqueSorted(scenarios.map((scenario) => scenario.workspace?.repo)),
    baseCommits: uniqueSorted(scenarios.map((scenario) => scenario.workspace?.base_commit)),
  };
}

function asNumber(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function compareTimestampDesc(left: string | null | undefined, right: string | null | undefined): number {
  const leftTime = left ? new Date(left).getTime() : 0;
  const rightTime = right ? new Date(right).getTime() : 0;
  return rightTime - leftTime;
}

export function buildLeaderboardRows(batches: EvaluationBatchListItem[]): LeaderboardRow[] {
  return batches
    .map((batch) => {
      const summary = batch.summary_json ?? {};
      return {
        batchId: trimText(batch.batch_id),
        createdAt: batch.created_at ?? null,
        status: batch.status ?? null,
        passRate: asNumber(summary.pass_rate),
        judgePassedRuns: typeof summary.judge_passed_runs === "number" ? summary.judge_passed_runs : 0,
        totalRuns: typeof summary.total_runs === "number" ? summary.total_runs : 0,
        families: uniqueSorted(summary.benchmark_families ?? []),
        splits: uniqueSorted(summary.benchmark_splits ?? []),
      };
    })
    .filter((row) => row.batchId)
    .sort((left, right) => {
      const passRateDelta = (right.passRate ?? -1) - (left.passRate ?? -1);
      if (passRateDelta !== 0) return passRateDelta;
      return compareTimestampDesc(left.createdAt, right.createdAt);
    });
}

export function listBatchExportFormats(scenarioRefs: EvaluationScenarioRef[]): string[] {
  return uniqueSorted(scenarioRefs.map((scenario) => scenario.export?.format));
}

export function resolveBatchExportFormat(scenarioRefs: EvaluationScenarioRef[], fallback = "generic_json"): string {
  return listBatchExportFormats(scenarioRefs)[0] ?? fallback;
}

const COMPARE_LABELS: Record<string, string> = {
  pass_rate: "Pass Rate",
  judge_passed_runs: "Judge Passed Runs",
  judge_failed_runs: "Judge Failed Runs",
  avg_total_tokens: "Avg Total Tokens",
  artifact_count_total: "Artifact Count",
};

function toCompareRow(key: string, metric: CompareDeltaMetric | null | undefined): CompareMetricRow {
  const baseline = typeof metric?.baseline === "number" ? metric.baseline : 0;
  const candidate = typeof metric?.candidate === "number" ? metric.candidate : 0;
  const delta = typeof metric?.delta === "number" ? metric.delta : candidate - baseline;
  const regression =
    (key === "pass_rate" || key === "judge_passed_runs") && delta < 0
      ? true
      : key === "judge_failed_runs" && delta > 0;
  return {
    key,
    label: COMPARE_LABELS[key] ?? key,
    baseline,
    candidate,
    delta,
    regression,
  };
}

export function buildCompareMetricRows(payload: ComparePayload | null | undefined): CompareMetricRow[] {
  const delta = payload?.delta ?? {};
  const rows: CompareMetricRow[] = [];

  for (const key of ["pass_rate", "judge_passed_runs", "judge_failed_runs", "avg_total_tokens", "artifact_count_total"]) {
    rows.push(toCompareRow(key, delta[key] as CompareDeltaMetric | null | undefined));
  }

  const scoreDelta = delta.avg_scores;
  if (scoreDelta && typeof scoreDelta === "object" && !Array.isArray(scoreDelta)) {
    const scoreMetrics = scoreDelta as Record<string, CompareDeltaMetric | null | undefined>;
    for (const key of Object.keys(scoreMetrics).sort((left, right) => left.localeCompare(right))) {
      const metric = scoreMetrics[key];
      const row = toCompareRow(`avg_scores.${key}`, metric);
      row.label = `Score: ${key}`;
      row.regression = row.delta < 0;
      rows.push(row);
    }
  }

  return rows;
}
