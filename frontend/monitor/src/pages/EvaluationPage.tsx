import React from "react";
import { Link, useNavigate } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import { postMonitorData, useMonitorData } from "../app/fetch";

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
  items?: Array<{
    batch_id?: string | null;
    kind?: string | null;
    status?: string | null;
    submitted_by_user_id?: string | null;
    agent_user_id?: string | null;
    created_at?: string | null;
    config_json?: {
      sandbox?: string | null;
      max_concurrent?: number | null;
      scenario_ids?: string[] | null;
    } | null;
    summary_json?: {
      total_runs?: number | null;
      running_runs?: number | null;
      completed_runs?: number | null;
      failed_runs?: number | null;
    } | null;
  }> | null;
  count?: number | null;
};

type EvaluationScenarioCatalogPayload = {
  items?: Array<{
    scenario_id?: string | null;
    name?: string | null;
    category?: string | null;
    sandbox?: string | null;
    message_count?: number | null;
    timeout_seconds?: number | null;
  }> | null;
  count?: number | null;
};

type EvaluationBatchCreatePayload = {
  batch?: {
    batch_id?: string | null;
  } | null;
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

function statusLabel(status: string | null | undefined): string {
  if (!status) return "未知";
  return BATCH_STATUS_LABELS[status] ?? status;
}

function statusTone(status: string | null | undefined): "pending" | "running" | "completed" | "failed" {
  if (!status) return "pending";
  return BATCH_STATUS_TONES[status] ?? "pending";
}

function summarizeBatch(batch: NonNullable<EvaluationBatchIndexPayload["items"]>[number]) {
  const summary = batch.summary_json ?? {};
  const config = batch.config_json ?? {};
  const totalRuns = asNumber(summary.total_runs);
  const runningRuns = asNumber(summary.running_runs);
  const completedRuns = asNumber(summary.completed_runs);
  const failedRuns = asNumber(summary.failed_runs);
  const finishedRuns = completedRuns + failedRuns;
  const progressPercent = totalRuns > 0 ? Math.min(100, Math.round((finishedRuns / totalRuns) * 100)) : 0;
  const scenarioCount = Array.isArray(config.scenario_ids) ? config.scenario_ids.length : 0;
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
  };
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
  const [createError, setCreateError] = React.useState<string | null>(null);
  const [createPending, setCreatePending] = React.useState(false);
  const [page, setPage] = React.useState(1);

  const overview = data?.overview ?? {};
  const runs = data?.runs ?? [];
  const selectedRun = data?.selected_run ?? {};
  const facts = selectedRun.facts ?? [];
  const limitations = data?.limitations ?? [];
  const batches = batchesData?.items ?? [];
  const scenarios = scenariosData?.items ?? [];

  const totalPages = Math.max(1, Math.ceil(batches.length / PAGE_SIZE));
  React.useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

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

  const batchRangeStart = batches.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const batchRangeEnd = Math.min(page * PAGE_SIZE, batches.length);

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
              Scenarios are the actual workloads a batch will run. They no longer sit in a standalone catalog section because they only matter while assembling a batch.
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
            <div className="evaluation-scenario-picker">
              <div className="evaluation-scenario-picker__header">
                <strong>Scenarios</strong>
                <span>{selectedScenarioIds.length} selected</span>
              </div>
              <div className="evaluation-scenario-list">
                {scenarios.length > 0 ? (
                  scenarios.map((scenario) => {
                    const scenarioId = scenario.scenario_id ?? "";
                    const selected = selectedScenarioIds.includes(scenarioId);
                    return (
                      <button
                        key={scenarioId || scenario.name}
                        type="button"
                        className={`evaluation-scenario-chip ${selected ? "evaluation-scenario-chip--selected" : ""}`}
                        onClick={() => scenarioId && toggleScenario(scenarioId)}
                      >
                        <span className="evaluation-scenario-chip__title mono">{scenarioId || scenario.name || "-"}</span>
                        <span className="evaluation-scenario-chip__meta">
                          {scenario.category ?? "uncategorized"} · {scenario.message_count ?? 0} msg · {scenario.timeout_seconds ?? "-"}s
                        </span>
                      </button>
                    );
                  })
                ) : (
                  <p className="surface-card__body">No evaluation scenarios found.</p>
                )}
              </div>
            </div>
            <div className="evaluation-create-panel__footer">
              {createError ? <span className="evaluation-batch-card__footer-note error">{createError}</span> : <span className="evaluation-batch-card__footer-note">Pending batches start from the batch detail page.</span>}
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
                      <span className="evaluation-batch-card__stat-label">Scenarios</span>
                      <strong className="evaluation-batch-card__stat-value">{metrics.scenarioCount}</strong>
                    </div>
                    <div className="evaluation-batch-card__stat">
                      <span className="evaluation-batch-card__stat-label">Sandbox</span>
                      <strong className="evaluation-batch-card__stat-value evaluation-batch-card__stat-value--compact">{metrics.sandbox}</strong>
                    </div>
                    <div className="evaluation-batch-card__stat">
                      <span className="evaluation-batch-card__stat-label">Concurrency</span>
                      <strong className="evaluation-batch-card__stat-value">{metrics.maxConcurrent || "-"}</strong>
                    </div>
                  </div>
                  <div className="evaluation-batch-card__meta">
                    <span><strong>Agent</strong> {batch.agent_user_id ?? "-"}</span>
                    <span><strong>Submitted</strong> {batch.submitted_by_user_id ?? "-"}</span>
                    <span><strong>Created</strong> {formatTimestamp(batch.created_at)}</span>
                  </div>
                  <div className="evaluation-batch-card__footer">
                    <span className="evaluation-batch-card__footer-note">{metrics.finishedRuns}/{metrics.totalRuns || 0} finished</span>
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
                  <td>{run.thread_id ? <Link to={`/threads/${run.thread_id}`}>{run.thread_id}</Link> : "-"}</td>
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
            {selectedRun.thread_id ? <Link to={`/threads/${selectedRun.thread_id}`}>{selectedRun.thread_id}</Link> : <span>-</span>}
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
