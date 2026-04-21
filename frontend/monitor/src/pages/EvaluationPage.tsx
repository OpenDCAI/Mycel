import React from "react";
import { Link, useNavigate } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import { buildMonitorPath, fetchAPI, postMonitorData, useMonitorData } from "../app/fetch";
import {
  buildCompareMetricRows,
  buildLeaderboardRows,
  buildScenarioFacetOptions,
  filterScenariosByBenchmark,
  listBatchExportFormats,
  summarizeSelectedScenarioContracts,
  type ComparePayload,
  type EvaluationBatchListItem,
  type EvaluationScenarioCatalogItem,
  type EvaluationScenarioRef,
} from "./evaluation-model";

type EvaluationPayload = {
  headline?: string | null;
  summary?: string | null;
  overview?: {
    total_runs?: number | null;
    running_runs?: number | null;
    completed_runs?: number | null;
    failed_runs?: number | null;
  } | null;
  runs?: Array<{
    run_id?: string | null;
    thread_id?: string | null;
    status?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    user_message?: string | null;
  }> | null;
  selected_run?: {
    run_id?: string | null;
    thread_id?: string | null;
    status?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    user_message?: string | null;
    facts?: Array<{ label?: string | null; value?: string | null }>;
  } | null;
  limitations?: string[] | null;
};

type EvaluationBatchIndexPayload = {
  items?: Array<
    EvaluationBatchListItem & {
      kind?: string | null;
      submitted_by_user_id?: string | null;
      agent_user_id?: string | null;
      config_json?: {
        sandbox?: string | null;
        max_concurrent?: number | null;
        scenario_ids?: string[] | null;
        scenario_refs?: EvaluationScenarioRef[] | null;
      } | null;
    }
  > | null;
  count?: number | null;
};

type EvaluationScenarioCatalogPayload = {
  items?: EvaluationScenarioCatalogItem[] | null;
  count?: number | null;
};

type EvaluationBatchCreatePayload = {
  batch?: {
    batch_id?: string | null;
  } | null;
};

type EvaluationCompareResponse = ComparePayload & {
  baseline_batch_id?: string | null;
  candidate_batch_id?: string | null;
  baseline?: Record<string, unknown> | null;
  candidate?: Record<string, unknown> | null;
};

type BatchMetrics = {
  totalRuns: number;
  runningRuns: number;
  completedRuns: number;
  failedRuns: number;
  finishedRuns: number;
  progressPercent: number;
  scenarioCount: number;
  sandbox: string;
  maxConcurrent: number;
  passRate: number | null;
  benchmarkFamilies: string[];
  exportFormats: string[];
};

const PAGE_SIZE = 8;

const BATCH_STATUS_LABELS: Record<string, string> = {
  pending: "待启动",
  running: "进行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  error: "错误",
};

const BATCH_STATUS_TONES: Record<string, "pending" | "running" | "completed" | "failed"> = {
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  cancelled: "failed",
  error: "failed",
};

function asNumber(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatPercent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "-";
}

function statusLabel(status: string | null | undefined): string {
  if (!status) return "未知";
  return BATCH_STATUS_LABELS[status] ?? status;
}

function statusTone(status: string | null | undefined): "pending" | "running" | "completed" | "failed" {
  if (!status) return "pending";
  return BATCH_STATUS_TONES[status] ?? "pending";
}

function summarizeBatch(batch: NonNullable<EvaluationBatchIndexPayload["items"]>[number]): BatchMetrics {
  const summary = batch.summary_json ?? {};
  const config = batch.config_json ?? {};
  const totalRuns = asNumber(summary.total_runs);
  const runningRuns = asNumber(summary.running_runs);
  const completedRuns = asNumber(summary.completed_runs);
  const failedRuns = asNumber(summary.failed_runs);
  const finishedRuns = completedRuns + failedRuns;
  const progressPercent = totalRuns > 0 ? Math.min(100, Math.round((finishedRuns / totalRuns) * 100)) : 0;
  const scenarioCount = Array.isArray(config.scenario_ids) ? config.scenario_ids.length : 0;
  const contract = summarizeSelectedScenarioContracts(config.scenario_refs ?? []);

  return {
    totalRuns,
    runningRuns,
    completedRuns,
    failedRuns,
    finishedRuns,
    progressPercent,
    scenarioCount,
    sandbox: config.sandbox ?? "-",
    maxConcurrent: asNumber(config.max_concurrent),
    passRate: typeof summary.pass_rate === "number" ? summary.pass_rate : null,
    benchmarkFamilies:
      Array.isArray(summary.benchmark_families) && summary.benchmark_families.length > 0
        ? [...summary.benchmark_families]
        : contract.families,
    exportFormats: contract.exportFormats.length > 0 ? contract.exportFormats : listBatchExportFormats(config.scenario_refs ?? []),
  };
}

function formatCompareValue(key: string, value: number): string {
  if (key === "pass_rate" || key.startsWith("avg_scores.")) return formatPercent(value);
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export default function EvaluationPage() {
  const navigate = useNavigate();
  const { data, error } = useMonitorData<EvaluationPayload>("/evaluation");
  const { data: batchesData, error: batchesError } = useMonitorData<EvaluationBatchIndexPayload>("/evaluation/batches");
  const { data: scenariosData, error: scenariosError } =
    useMonitorData<EvaluationScenarioCatalogPayload>("/evaluation/scenarios");
  const [agentUserId, setAgentUserId] = React.useState("");
  const [sandbox, setSandbox] = React.useState("local");
  const [maxConcurrent, setMaxConcurrent] = React.useState(1);
  const [selectedScenarioIds, setSelectedScenarioIds] = React.useState<string[]>([]);
  const [selectedFamily, setSelectedFamily] = React.useState("");
  const [selectedInstanceId, setSelectedInstanceId] = React.useState("");
  const [selectedJudgeType, setSelectedJudgeType] = React.useState("");
  const [selectedExportFormat, setSelectedExportFormat] = React.useState("");
  const [createError, setCreateError] = React.useState<string | null>(null);
  const [createPending, setCreatePending] = React.useState(false);
  const [page, setPage] = React.useState(1);
  const [baselineBatchId, setBaselineBatchId] = React.useState("");
  const [candidateBatchId, setCandidateBatchId] = React.useState("");
  const [comparePending, setComparePending] = React.useState(false);
  const [compareError, setCompareError] = React.useState<string | null>(null);
  const [compareData, setCompareData] = React.useState<EvaluationCompareResponse | null>(null);

  const overview = data?.overview ?? {};
  const runs = data?.runs ?? [];
  const selectedRun = data?.selected_run ?? {};
  const facts = selectedRun.facts ?? [];
  const limitations = data?.limitations ?? [];
  const batches = batchesData?.items ?? [];
  const scenarios = scenariosData?.items ?? [];
  const scenarioFacetOptions = buildScenarioFacetOptions(scenarios, selectedFamily);
  const filteredScenarios = filterScenariosByBenchmark(scenarios, {
    family: selectedFamily,
    instanceId: selectedInstanceId,
    judgeType: selectedJudgeType,
    exportFormat: selectedExportFormat,
  });
  const selectedScenarios = scenarios.filter((scenario) => selectedScenarioIds.includes(scenario.scenario_id ?? ""));
  const selectedContracts = summarizeSelectedScenarioContracts(selectedScenarios);
  const leaderboardRows = buildLeaderboardRows(batches);
  const compareRows = buildCompareMetricRows(compareData);

  const totalPages = Math.max(1, Math.ceil(batches.length / PAGE_SIZE));

  React.useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  React.useEffect(() => {
    if (selectedFamily && !scenarioFacetOptions.families.includes(selectedFamily)) {
      setSelectedFamily("");
    }
    if (selectedInstanceId && !scenarioFacetOptions.instanceIds.includes(selectedInstanceId)) {
      setSelectedInstanceId("");
    }
    if (selectedJudgeType && !scenarioFacetOptions.judgeTypes.includes(selectedJudgeType)) {
      setSelectedJudgeType("");
    }
    if (selectedExportFormat && !scenarioFacetOptions.exportFormats.includes(selectedExportFormat)) {
      setSelectedExportFormat("");
    }
  }, [
    scenarioFacetOptions.exportFormats,
    scenarioFacetOptions.families,
    scenarioFacetOptions.instanceIds,
    scenarioFacetOptions.judgeTypes,
    selectedExportFormat,
    selectedFamily,
    selectedInstanceId,
    selectedJudgeType,
  ]);

  React.useEffect(() => {
    if (baselineBatchId || candidateBatchId || batches.length < 2) return;
    const rankedBatchIds = [...leaderboardRows, ...batches.map((batch) => ({ batchId: batch.batch_id ?? "" }))]
      .map((row) => row.batchId)
      .filter(Boolean);
    if (rankedBatchIds.length < 2) return;
    setBaselineBatchId(rankedBatchIds[0]);
    setCandidateBatchId(rankedBatchIds.find((batchId) => batchId !== rankedBatchIds[0]) ?? "");
  }, [baselineBatchId, batches, candidateBatchId, leaderboardRows]);

  const visibleBatches = React.useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return batches.slice(start, start + PAGE_SIZE);
  }, [batches, page]);

  if (error) return <ErrorState title="Evaluation" error={error} />;
  if (batchesError) return <ErrorState title="Evaluation batches" error={batchesError} />;
  if (scenariosError) return <ErrorState title="Evaluation scenarios" error={scenariosError} />;
  if (!data || !batchesData || !scenariosData) return <div>Loading...</div>;

  function toggleScenario(scenarioId: string) {
    setSelectedScenarioIds((current) =>
      current.includes(scenarioId) ? current.filter((item) => item !== scenarioId) : [...current, scenarioId],
    );
  }

  async function createBatch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatePending(true);
    setCreateError(null);
    try {
      const result = await postMonitorData<EvaluationBatchCreatePayload>("/evaluation/batches", {
        agent_user_id: agentUserId.trim(),
        scenario_ids: selectedScenarioIds,
        sandbox,
        max_concurrent: maxConcurrent,
      });
      const batchId = result.batch?.batch_id;
      if (!batchId) throw new Error("Evaluation batch create response did not include batch_id.");
      navigate(`/evaluation/batches/${batchId}`);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatePending(false);
    }
  }

  async function loadComparison() {
    if (!baselineBatchId || !candidateBatchId) {
      setCompareError("Choose both baseline and candidate batches before running compare.");
      setCompareData(null);
      return;
    }
    if (baselineBatchId === candidateBatchId) {
      setCompareError("Baseline and candidate must be different batches.");
      setCompareData(null);
      return;
    }

    setComparePending(true);
    setCompareError(null);
    try {
      const result = await fetchAPI<EvaluationCompareResponse>(
        buildMonitorPath("/evaluation/compare", {
          baseline_batch_id: baselineBatchId,
          candidate_batch_id: candidateBatchId,
        }),
      );
      setCompareData(result);
    } catch (err: unknown) {
      setCompareError(err instanceof Error ? err.message : String(err));
      setCompareData(null);
    } finally {
      setComparePending(false);
    }
  }

  const batchRangeStart = batches.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const batchRangeEnd = Math.min(page * PAGE_SIZE, batches.length);
  const benchmarkSurfaceAvailable = scenarioFacetOptions.benchmarkScenarioCount > 0;
  const hasCompareRegression = compareRows.some((row) => row.regression);

  return (
    <div className="page">
      <h1>Evaluation</h1>
      <p className="description">{data.headline ?? "Evaluation workbench."}</p>

      <section className="surface-section">
        <h2>Workbench Overview</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">Total Runs</p>
            <p className="surface-card__value">{overview.total_runs ?? 0}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Running</p>
            <p className="surface-card__value">{overview.running_runs ?? 0}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Completed</p>
            <p className="surface-card__value">{overview.completed_runs ?? 0}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Failed</p>
            <p className="surface-card__value">{overview.failed_runs ?? 0}</p>
          </article>
        </div>
      </section>

      <section className="surface-section">
        <h2>Workbench Summary</h2>
        <p className="surface-card__body">{data.summary ?? "No evaluation summary available."}</p>
      </section>

      <section className="surface-section">
        <div className="evaluation-batches-header">
          <div>
            <h2>Evaluation Batches</h2>
          </div>
        </div>

        <article className="evaluation-create-panel">
          <div className="evaluation-create-panel__intro">
            <p className="evaluation-create-panel__eyebrow">Builder</p>
            <h3>Create Batch</h3>
            <p className="surface-card__body">
              Benchmark controls read directly from the monitor scenario catalog. If the backend does not publish
              benchmark metadata yet, the builder falls back to raw scenario selection and calls that gap out instead of
              inventing values.
            </p>
          </div>
          <form className="evaluation-create-form" onSubmit={(event) => void createBatch(event)}>
            <div className="evaluation-create-form__grid">
              <label className="evaluation-create-form__field">
                <span>Agent user id</span>
                <input value={agentUserId} onChange={(event) => setAgentUserId(event.target.value)} />
              </label>
              <label className="evaluation-create-form__field">
                <span>Sandbox</span>
                <input value={sandbox} onChange={(event) => setSandbox(event.target.value)} />
              </label>
              <label className="evaluation-create-form__field">
                <span>Max concurrent</span>
                <input
                  min={1}
                  type="number"
                  value={maxConcurrent}
                  onChange={(event) => setMaxConcurrent(Number(event.target.value))}
                />
              </label>
            </div>

            <div className="evaluation-benchmark-filters">
              <div className="evaluation-benchmark-filters__header">
                <strong>Benchmark Contract</strong>
                <span>
                  {benchmarkSurfaceAvailable
                    ? `${scenarioFacetOptions.benchmarkScenarioCount} scenario contracts expose benchmark metadata`
                    : "Current backend catalog exposes no benchmark metadata"}
                </span>
              </div>
              <div className="evaluation-create-form__grid">
                <label className="evaluation-create-form__field">
                  <span>Family</span>
                  <select
                    value={selectedFamily}
                    onChange={(event) => {
                      setSelectedFamily(event.target.value);
                      setSelectedInstanceId("");
                    }}
                    disabled={!benchmarkSurfaceAvailable}
                  >
                    <option value="">All families</option>
                    {scenarioFacetOptions.families.map((family) => (
                      <option key={family} value={family}>
                        {family}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="evaluation-create-form__field">
                  <span>Instance</span>
                  <select
                    value={selectedInstanceId}
                    onChange={(event) => setSelectedInstanceId(event.target.value)}
                    disabled={scenarioFacetOptions.instanceIds.length === 0}
                  >
                    <option value="">All instances</option>
                    {scenarioFacetOptions.instanceIds.map((instanceId) => (
                      <option key={instanceId} value={instanceId}>
                        {instanceId}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="evaluation-create-form__field">
                  <span>Judge profile</span>
                  <select
                    value={selectedJudgeType}
                    onChange={(event) => setSelectedJudgeType(event.target.value)}
                    disabled={scenarioFacetOptions.judgeTypes.length === 0}
                  >
                    <option value="">All judge profiles</option>
                    {scenarioFacetOptions.judgeTypes.map((judgeType) => (
                      <option key={judgeType} value={judgeType}>
                        {judgeType}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="evaluation-create-form__field">
                  <span>Export profile</span>
                  <select
                    value={selectedExportFormat}
                    onChange={(event) => setSelectedExportFormat(event.target.value)}
                    disabled={scenarioFacetOptions.exportFormats.length === 0}
                  >
                    <option value="">All export profiles</option>
                    {scenarioFacetOptions.exportFormats.map((exportFormat) => (
                      <option key={exportFormat} value={exportFormat}>
                        {exportFormat}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {!benchmarkSurfaceAvailable ? (
                <p className="evaluation-scenario-picker__hint">
                  Blocked by current backend data: `/api/monitor/evaluation/scenarios` returns no benchmark family,
                  instance, judge, or export profile metadata yet.
                </p>
              ) : null}
            </div>

            <div className="evaluation-scenario-picker">
              <div className="evaluation-scenario-picker__header">
                <strong>Scenarios</strong>
                <span>
                  {selectedScenarioIds.length} selected · {filteredScenarios.length}/{scenarios.length} visible
                </span>
              </div>
              <p className="evaluation-scenario-picker__hint">
                Scenario selection is still the source of truth for batch creation. Benchmark fields above only filter
                what the backend already publishes in the scenario catalog.
              </p>
              <div className="evaluation-scenario-list">
                {filteredScenarios.length > 0 ? (
                  filteredScenarios.map((scenario) => {
                    const scenarioId = scenario.scenario_id ?? "";
                    const selected = selectedScenarioIds.includes(scenarioId);
                    return (
                      <button
                        key={scenarioId || scenario.name}
                        type="button"
                        aria-pressed={selected}
                        className={`evaluation-scenario-chip ${selected ? "evaluation-scenario-chip--selected" : ""}`}
                        onClick={() => scenarioId && toggleScenario(scenarioId)}
                      >
                        <span className="evaluation-scenario-chip__title mono">{scenarioId || scenario.name || "-"}</span>
                        <span className="evaluation-scenario-chip__meta">
                          {scenario.benchmark?.family ?? scenario.category ?? "uncategorized"} ·{" "}
                          {scenario.benchmark?.instance_id ?? `${scenario.message_count ?? 0} msg`} · judge{" "}
                          {scenario.judge_type ?? "-"} · export {scenario.export_format ?? "-"}
                        </span>
                      </button>
                    );
                  })
                ) : (
                  <p className="surface-card__body">No evaluation scenarios match the selected benchmark filters.</p>
                )}
              </div>
            </div>

            <div className="evaluation-contract-preview">
              <div className="evaluation-contract-preview__header">
                <strong>Resolved Contract Preview</strong>
                <span>{selectedContracts.totalCount} scenario refs</span>
              </div>
              <div className="evaluation-contract-preview__grid">
                <div>
                  <strong>Families</strong>
                  <span>{selectedContracts.families.join(", ") || "-"}</span>
                </div>
                <div>
                  <strong>Instances</strong>
                  <span>{selectedContracts.instances.join(", ") || "-"}</span>
                </div>
                <div>
                  <strong>Judge profiles</strong>
                  <span>{selectedContracts.judgeTypes.join(", ") || "-"}</span>
                </div>
                <div>
                  <strong>Export profiles</strong>
                  <span>{selectedContracts.exportFormats.join(", ") || "-"}</span>
                </div>
                <div>
                  <strong>Repos</strong>
                  <span>{selectedContracts.repos.join(", ") || "-"}</span>
                </div>
                <div>
                  <strong>Base commits</strong>
                  <span>{selectedContracts.baseCommits.join(", ") || "-"}</span>
                </div>
              </div>
              {selectedContracts.missingBenchmarkMetadataCount > 0 ? (
                <p className="evaluation-scenario-picker__hint">
                  {selectedContracts.missingBenchmarkMetadataCount} selected scenario refs do not publish benchmark
                  metadata yet, so batch creation can only persist raw scenario ids for them.
                </p>
              ) : null}
            </div>

            <div className="evaluation-create-panel__footer">
              {createError ? (
                <span className="evaluation-batch-card__footer-note error">{createError}</span>
              ) : (
                <span className="evaluation-batch-card__footer-note">
                  Pending batches start from the batch detail page.
                </span>
              )}
              <button
                type="submit"
                className="monitor-action-button"
                disabled={createPending || agentUserId.trim() === "" || selectedScenarioIds.length === 0}
              >
                {createPending ? "Creating..." : "Create batch"}
              </button>
            </div>
          </form>
        </article>

        {batches.length > 0 ? (
          <div className="evaluation-pagination evaluation-pagination--inline">
            <span className="evaluation-pagination__meta">
              Showing {batchRangeStart}-{batchRangeEnd} of {batches.length} batches
            </span>
            {totalPages > 1 ? (
              <>
                <button
                  type="button"
                  className="monitor-action-button"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  Previous
                </button>
                <span className="evaluation-pagination__meta">Page {page} / {totalPages}</span>
                <button
                  type="button"
                  className="monitor-action-button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                >
                  Next
                </button>
              </>
            ) : null}
          </div>
        ) : null}

        {visibleBatches.length > 0 ? (
          <div className="evaluation-batch-grid">
            {visibleBatches.map((batch) => {
              const batchId = batch.batch_id ?? "-";
              const metrics = summarizeBatch(batch);
              const tone = statusTone(batch.status);
              return (
                <article key={batchId} className="evaluation-batch-card">
                  <div className="evaluation-batch-card__header">
                    <div className="evaluation-batch-card__heading">
                      <p className="evaluation-batch-card__eyebrow">{batch.kind ?? "scenario_batch"}</p>
                      {batch.batch_id ? (
                        <Link className="evaluation-batch-card__title mono" to={`/evaluation/batches/${batch.batch_id}`}>
                          {batch.batch_id}
                        </Link>
                      ) : (
                        <span className="evaluation-batch-card__title mono">-</span>
                      )}
                    </div>
                    <span className={`evaluation-batch-card__status evaluation-batch-card__status--${tone}`}>
                      {statusLabel(batch.status)}
                    </span>
                  </div>
                  <div className="evaluation-batch-card__progress-block">
                    <div className="evaluation-batch-card__progress-track" aria-hidden="true">
                      <div
                        className={`evaluation-batch-card__progress-fill evaluation-batch-card__progress-fill--${tone}`}
                        style={{ width: `${metrics.progressPercent}%` }}
                      />
                    </div>
                    <p className="evaluation-batch-card__progress-copy">
                      {metrics.completedRuns} completed · {metrics.failedRuns} failed · {metrics.runningRuns} running
                    </p>
                  </div>
                  <div className="evaluation-batch-card__stats">
                    <div className="evaluation-batch-card__stat">
                      <span className="evaluation-batch-card__stat-label">Runs</span>
                      <strong className="evaluation-batch-card__stat-value">{metrics.totalRuns}</strong>
                    </div>
                    <div className="evaluation-batch-card__stat">
                      <span className="evaluation-batch-card__stat-label">Pass rate</span>
                      <strong className="evaluation-batch-card__stat-value">{formatPercent(metrics.passRate)}</strong>
                    </div>
                    <div className="evaluation-batch-card__stat">
                      <span className="evaluation-batch-card__stat-label">Sandbox</span>
                      <strong className="evaluation-batch-card__stat-value evaluation-batch-card__stat-value--compact">
                        {metrics.sandbox}
                      </strong>
                    </div>
                    <div className="evaluation-batch-card__stat">
                      <span className="evaluation-batch-card__stat-label">Concurrency</span>
                      <strong className="evaluation-batch-card__stat-value">{metrics.maxConcurrent || "-"}</strong>
                    </div>
                  </div>
                  <div className="evaluation-batch-card__meta">
                    <span>
                      <strong>Agent</strong> {batch.agent_user_id ?? "-"}
                    </span>
                    <span>
                      <strong>Families</strong> {metrics.benchmarkFamilies.join(", ") || "-"}
                    </span>
                    <span>
                      <strong>Export</strong> {metrics.exportFormats.join(", ") || "-"}
                    </span>
                    <span>
                      <strong>Created</strong> {formatTimestamp(batch.created_at)}
                    </span>
                  </div>
                  <div className="evaluation-batch-card__footer">
                    <span className="evaluation-batch-card__footer-note">
                      {metrics.finishedRuns}/{metrics.totalRuns || 0} finished
                    </span>
                    {batch.batch_id ? (
                      <Link className="evaluation-batch-card__open-link" to={`/evaluation/batches/${batch.batch_id}`}>
                        Open batch
                      </Link>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <article className="surface-card">
            <p className="surface-card__body">No evaluation batches yet.</p>
          </article>
        )}
      </section>

      <section className="surface-section">
        <h2>Leaderboard</h2>
        {leaderboardRows.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Batch</th>
                <th>Status</th>
                <th>Pass Rate</th>
                <th>Judge Passed</th>
                <th>Total Runs</th>
                <th>Families</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {leaderboardRows.slice(0, 6).map((row) => (
                <tr key={row.batchId}>
                  <td className="mono">
                    <Link to={`/evaluation/batches/${row.batchId}`}>{row.batchId}</Link>
                  </td>
                  <td>{row.status ?? "-"}</td>
                  <td>{formatPercent(row.passRate)}</td>
                  <td>{row.judgePassedRuns}</td>
                  <td>{row.totalRuns}</td>
                  <td>{row.families.join(", ") || "-"}</td>
                  <td>{formatTimestamp(row.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <article className="surface-card">
            <p className="surface-card__body">Leaderboard populates once batches have aggregate judge metrics.</p>
          </article>
        )}
      </section>

      <section className="surface-section">
        <h2>Compare</h2>
        <div className="evaluation-compare-panel">
          <div className="evaluation-create-form__grid">
            <label className="evaluation-create-form__field">
              <span>Baseline batch</span>
              <select value={baselineBatchId} onChange={(event) => setBaselineBatchId(event.target.value)}>
                <option value="">Select baseline</option>
                {batches.map((batch) => (
                  <option key={batch.batch_id ?? ""} value={batch.batch_id ?? ""}>
                    {batch.batch_id ?? "-"}
                  </option>
                ))}
              </select>
            </label>
            <label className="evaluation-create-form__field">
              <span>Candidate batch</span>
              <select value={candidateBatchId} onChange={(event) => setCandidateBatchId(event.target.value)}>
                <option value="">Select candidate</option>
                {batches.map((batch) => (
                  <option key={batch.batch_id ?? ""} value={batch.batch_id ?? ""}>
                    {batch.batch_id ?? "-"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="evaluation-create-panel__footer">
            {compareError ? (
              <span className="evaluation-batch-card__footer-note error">{compareError}</span>
            ) : (
              <span className="evaluation-batch-card__footer-note">
                Compare hits `/api/monitor/evaluation/compare` directly and reports regressions when pass rate drops or
                judge failures rise.
              </span>
            )}
            <button type="button" className="monitor-action-button" disabled={comparePending} onClick={() => void loadComparison()}>
              {comparePending ? "Comparing..." : "Compare batches"}
            </button>
          </div>
          {compareData ? (
            <div className="evaluation-compare-result">
              <div className="evaluation-compare-result__header">
                <strong>Comparison Result</strong>
                <span>{hasCompareRegression ? "Regression detected" : "No regression signal detected"}</span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Baseline</th>
                    <th>Candidate</th>
                    <th>Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {compareRows.map((row) => (
                    <tr key={row.key}>
                      <td>{row.label}</td>
                      <td>{formatCompareValue(row.key, row.baseline)}</td>
                      <td>{formatCompareValue(row.key, row.candidate)}</td>
                      <td className={row.regression ? "error" : ""}>
                        {row.delta > 0 ? "+" : ""}
                        {formatCompareValue(row.key, row.delta)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </section>

      <section className="surface-section">
        <h2>Recent Runs</h2>
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Thread</th>
              <th>Status</th>
              <th>Started</th>
              <th>Finished</th>
              <th>User Message</th>
            </tr>
          </thead>
          <tbody>
            {runs.length > 0 ? (
              runs.map((run) => (
                <tr key={run.run_id ?? `${run.thread_id}-${run.started_at}`}>
                  <td className="mono">
                    {run.run_id ? <Link to={`/evaluation/runs/${run.run_id}`}>{run.run_id}</Link> : "-"}
                  </td>
                  <td>{run.thread_id || "-"}</td>
                  <td>{run.status ?? "-"}</td>
                  <td>{run.started_at ?? "-"}</td>
                  <td>{run.finished_at ?? "-"}</td>
                  <td>{run.user_message ?? "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6}>No persisted evaluation runs yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="surface-section">
        <h2>Current Run</h2>
        <div className="info-grid">
          <div>
            <strong>Thread</strong>
            <span>{selectedRun.thread_id || "-"}</span>
          </div>
          <div>
            <strong>Run ID</strong>
            {selectedRun.run_id ? (
              <Link className="mono" to={`/evaluation/runs/${selectedRun.run_id}`}>
                {selectedRun.run_id}
              </Link>
            ) : (
              <span className="mono">-</span>
            )}
          </div>
          <div>
            <strong>Status</strong>
            <span>{selectedRun.status ?? "-"}</span>
          </div>
          <div>
            <strong>Started At</strong>
            <span>{selectedRun.started_at ?? "-"}</span>
          </div>
          <div>
            <strong>Finished At</strong>
            <span>{selectedRun.finished_at ?? "-"}</span>
          </div>
          <div>
            <strong>User Message</strong>
            <span>{selectedRun.user_message ?? "-"}</span>
          </div>
        </div>
      </section>

      <section className="surface-section">
        <h2>Run Facts</h2>
        <div className="info-grid">
          {facts.map((fact) => (
            <div key={`${fact.label}-${fact.value}`}>
              <strong>{fact.label ?? "-"}</strong>
              <span>{fact.value ?? "-"}</span>
            </div>
          ))}
        </div>
      </section>

      {limitations.length > 0 ? (
        <section className="surface-section">
          <h2>Notes</h2>
          <ul className="surface-list">
            {limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
