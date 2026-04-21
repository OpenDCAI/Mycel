import React from "react";
import { Link, useParams } from "react-router-dom";

import { buildMonitorPath, fetchAPI, postMonitorData, useMonitorData, type MonitorFetchError } from "../app/fetch";
import ErrorState from "../components/ErrorState";
import {
  listBatchExportFormats,
  resolveBatchExportFormat,
  summarizeSelectedScenarioContracts,
  type EvaluationBatchSummary,
  type EvaluationScenarioRef,
} from "./evaluation-model";

type EvaluationBatchDetailPayload = {
  batch?: {
    batch_id?: string | null;
    kind?: string | null;
    status?: string | null;
    config_json?: {
      sandbox?: string | null;
      max_concurrent?: number | null;
      scenario_ids?: string[] | null;
      scenario_refs?: EvaluationScenarioRef[] | null;
    } | null;
    summary_json?: EvaluationBatchSummary | null;
  } | null;
  runs?: Array<{
    batch_run_id?: string | null;
    scenario_id?: string | null;
    status?: string | null;
    thread_id?: string | null;
    eval_run_id?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    summary_json?: {
      instance_id?: string | null;
      benchmark_family?: string | null;
      benchmark_split?: string | null;
      judge_type?: string | null;
      judge_verdict?: string | null;
      export_format?: string | null;
      export_key?: string | null;
      artifact_count?: number | null;
      error?: string | null;
    } | null;
  }> | null;
  aggregate?: EvaluationBatchSummary | null;
};

type EvaluationBatchStartPayload = {
  accepted: boolean;
  batch?: EvaluationBatchDetailPayload["batch"];
};

type EvaluationBatchAggregatePayload = {
  batch_id?: string | null;
  status?: string | null;
  summary?: EvaluationBatchSummary | null;
};

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatPercent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "-";
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export default function EvaluationBatchDetailPage() {
  const params = useParams<{ batchId: string }>();
  const batchId = params.batchId ?? "";
  const { data, error } = useMonitorData<EvaluationBatchDetailPayload>(`/evaluation/batches/${batchId}`);
  const { data: aggregateData, error: aggregateError } =
    useMonitorData<EvaluationBatchAggregatePayload>(`/evaluation/batches/${batchId}/aggregate`);
  const [batchData, setBatchData] = React.useState<EvaluationBatchDetailPayload | null>(null);
  const [startMessage, setStartMessage] = React.useState<string | null>(null);
  const [startError, setStartError] = React.useState<string | null>(null);
  const [startPending, setStartPending] = React.useState(false);
  const [exportFormat, setExportFormat] = React.useState("generic_json");
  const [exportPending, setExportPending] = React.useState(false);
  const [exportError, setExportError] = React.useState<string | null>(null);
  const [exportMessage, setExportMessage] = React.useState<string | null>(null);
  const [exportPreview, setExportPreview] = React.useState<Record<string, unknown> | null>(null);

  React.useEffect(() => {
    if (!data) return;
    setBatchData(data);
    setStartMessage(null);
    setStartError(null);
    setStartPending(false);
    const scenarioRefs = data.batch?.config_json?.scenario_refs ?? [];
    setExportFormat(resolveBatchExportFormat(scenarioRefs));
  }, [data]);

  if (error) return <ErrorState title={`Evaluation batch ${batchId}`} error={error} />;
  if (!batchData) return <div>Loading...</div>;

  const batch = batchData.batch ?? {};
  const config = batch.config_json ?? {};
  const summary = aggregateData?.summary ?? batchData.aggregate ?? batch.summary_json ?? {};
  const runs = batchData.runs ?? [];
  const scenarioRefs = config.scenario_refs ?? [];
  const contractSummary = summarizeSelectedScenarioContracts(scenarioRefs);
  const exportFormats = listBatchExportFormats(scenarioRefs);
  const progressSummary = `${summary.completed_runs ?? 0} completed / ${summary.failed_runs ?? 0} failed / ${
    summary.running_runs ?? 0
  } running`;

  async function startBatch() {
    setStartPending(true);
    setStartMessage(null);
    setStartError(null);
    try {
      const result = await postMonitorData<EvaluationBatchStartPayload>(`/evaluation/batches/${batchId}/start`);
      setBatchData((current) => ({
        ...(current ?? {}),
        batch: {
          ...(current?.batch ?? {}),
          ...(result.batch ?? {}),
        },
      }));
      setStartMessage(result.accepted ? "Batch execution scheduled." : "Batch execution was not accepted.");
    } catch (err: unknown) {
      const fetchError = err as MonitorFetchError;
      setStartError(fetchError.message);
    } finally {
      setStartPending(false);
    }
  }

  async function exportBatch() {
    setExportPending(true);
    setExportError(null);
    setExportMessage(null);
    try {
      const result = await fetchAPI<Record<string, unknown>>(
        buildMonitorPath(`/evaluation/batches/${batchId}/export`, {
          format: exportFormat || undefined,
        }),
      );
      downloadJson(`${batchId}-${exportFormat || "generic_json"}.json`, result);
      setExportPreview(result);
      setExportMessage(
        `Downloaded ${batchId}-${exportFormat || "generic_json"}.json with ${Object.keys(result).length} top-level keys.`,
      );
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : String(err));
      setExportPreview(null);
    } finally {
      setExportPending(false);
    }
  }

  return (
    <div className="page">
      <h1>{`Evaluation Batch ${batch.batch_id ?? batchId}`}</h1>
      <p className="description">Scenario batch state, benchmark contract echo, aggregate summary, and export controls.</p>

      <section className="surface-section">
        <h2>Batch State</h2>
        <div className="info-grid">
          <div>
            <strong>Status</strong>
            <span>{batch.status ?? "-"}</span>
          </div>
          <div>
            <strong>Kind</strong>
            <span>{batch.kind ?? "-"}</span>
          </div>
          <div>
            <strong>Sandbox</strong>
            <span>{config.sandbox ?? "-"}</span>
          </div>
          <div>
            <strong>Max Concurrent</strong>
            <span>{config.max_concurrent ?? "-"}</span>
          </div>
          <div>
            <strong>Total Runs</strong>
            <span>{summary.total_runs ?? runs.length}</span>
          </div>
          <div>
            <strong>Progress</strong>
            <span>{progressSummary}</span>
          </div>
          <div>
            <strong>Surface</strong>
            <Link to="/evaluation">Evaluation</Link>
          </div>
        </div>
      </section>

      {batch.status === "pending" || startMessage || startError ? (
        <section className="surface-section">
          <h2>Execution</h2>
          {batch.status === "pending" ? (
            <button
              type="button"
              className="monitor-action-button"
              disabled={startPending}
              onClick={() => void startBatch()}
            >
              Start evaluation batch
            </button>
          ) : null}
          {startMessage ? <p className="description">{startMessage}</p> : null}
          {startError ? <p className="description error">{startError}</p> : null}
        </section>
      ) : null}

      <section className="surface-section">
        <h2>Benchmark Contract</h2>
        <div className="info-grid">
          <div>
            <strong>Families</strong>
            <span>{contractSummary.families.join(", ") || "-"}</span>
          </div>
          <div>
            <strong>Instances</strong>
            <span>{contractSummary.instances.join(", ") || "-"}</span>
          </div>
          <div>
            <strong>Judge profiles</strong>
            <span>{contractSummary.judgeTypes.join(", ") || "-"}</span>
          </div>
          <div>
            <strong>Export profiles</strong>
            <span>{contractSummary.exportFormats.join(", ") || "-"}</span>
          </div>
          <div>
            <strong>Repos</strong>
            <span>{contractSummary.repos.join(", ") || "-"}</span>
          </div>
          <div>
            <strong>Base commits</strong>
            <span>{contractSummary.baseCommits.join(", ") || "-"}</span>
          </div>
        </div>
        {contractSummary.missingBenchmarkMetadataCount > 0 ? (
          <p className="description">
            {contractSummary.missingBenchmarkMetadataCount} scenario refs were created without benchmark metadata. This
            is a real backend data gap, not a frontend omission.
          </p>
        ) : null}
        {scenarioRefs.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Family</th>
                <th>Instance</th>
                <th>Judge</th>
                <th>Export</th>
                <th>Repo</th>
                <th>Base Commit</th>
              </tr>
            </thead>
            <tbody>
              {scenarioRefs.map((scenario) => (
                <tr key={scenario.scenario_id ?? scenario.name}>
                  <td className="mono">{scenario.scenario_id ?? scenario.name ?? "-"}</td>
                  <td>{scenario.benchmark?.family ?? "-"}</td>
                  <td>{scenario.benchmark?.instance_id ?? "-"}</td>
                  <td>{scenario.judge_config?.type ?? "-"}</td>
                  <td>{scenario.export?.format ?? "-"}</td>
                  <td>{scenario.workspace?.repo ?? "-"}</td>
                  <td className="mono">{scenario.workspace?.base_commit ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <article className="surface-card">
            <p className="surface-card__body">No scenario refs were persisted for this batch.</p>
          </article>
        )}
      </section>

      <section className="surface-section">
        <h2>Aggregate Summary</h2>
        {aggregateError ? <p className="description error">{aggregateError.message}</p> : null}
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">Pass Rate</p>
            <p className="surface-card__value">{formatPercent(summary.pass_rate)}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Judge Passed</p>
            <p className="surface-card__value">{summary.judge_passed_runs ?? 0}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Judge Failed</p>
            <p className="surface-card__value">{summary.judge_failed_runs ?? 0}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Artifacts</p>
            <p className="surface-card__value">{summary.artifact_count_total ?? 0}</p>
          </article>
        </div>
        <div className="info-grid">
          <div>
            <strong>Benchmark families</strong>
            <span>{summary.benchmark_families?.join(", ") || "-"}</span>
          </div>
          <div>
            <strong>Benchmark splits</strong>
            <span>{summary.benchmark_splits?.join(", ") || "-"}</span>
          </div>
          <div>
            <strong>Avg total tokens</strong>
            <span>{summary.avg_total_tokens ?? "-"}</span>
          </div>
          <div>
            <strong>Avg scores</strong>
            <span>
              {summary.avg_scores && Object.keys(summary.avg_scores).length > 0
                ? Object.entries(summary.avg_scores)
                    .map(([key, value]) => `${key}:${value}`)
                    .join(", ")
                : "-"}
            </span>
          </div>
        </div>
      </section>

      <section className="surface-section">
        <h2>Export</h2>
        <div className="evaluation-compare-panel">
          <div className="evaluation-create-form__grid">
            <label className="evaluation-create-form__field">
              <span>Export format</span>
              <select value={exportFormat} onChange={(event) => setExportFormat(event.target.value)}>
                {[...(exportFormats.length > 0 ? exportFormats : ["generic_json"])].map((format) => (
                  <option key={format} value={format}>
                    {format}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="evaluation-create-panel__footer">
            {exportError ? (
              <span className="evaluation-batch-card__footer-note error">{exportError}</span>
            ) : (
              <span className="evaluation-batch-card__footer-note">
                Download hits `/api/monitor/evaluation/batches/{batchId}/export` and saves the live JSON payload locally.
              </span>
            )}
            <button
              type="button"
              className="monitor-action-button"
              disabled={exportPending}
              onClick={() => void exportBatch()}
            >
              {exportPending ? "Exporting..." : "Download export"}
            </button>
          </div>
          {exportMessage ? <p className="description">{exportMessage}</p> : null}
          {exportPreview ? (
            <details className="evaluation-json-panel" open>
              <summary>Last export preview</summary>
              <pre>{JSON.stringify(exportPreview, null, 2)}</pre>
            </details>
          ) : null}
        </div>
      </section>

      <section className="surface-section">
        <h2>Batch Runs</h2>
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Instance</th>
              <th>Status</th>
              <th>Judge</th>
              <th>Export</th>
              <th>Artifacts</th>
              <th>Thread</th>
              <th>Eval Run</th>
              <th>Started</th>
              <th>Finished</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => {
              const runSummary = run.summary_json ?? {};
              return (
                <tr key={run.batch_run_id ?? run.scenario_id}>
                  <td className="mono">{run.scenario_id ?? "-"}</td>
                  <td className="mono">{runSummary.instance_id ?? "-"}</td>
                  <td>{run.status ?? "-"}</td>
                  <td>{runSummary.judge_verdict ?? runSummary.error ?? "-"}</td>
                  <td>{runSummary.export_format ?? "-"}</td>
                  <td>{runSummary.artifact_count ?? "-"}</td>
                  <td>{run.thread_id || "-"}</td>
                  <td>{run.eval_run_id ? <Link to={`/evaluation/runs/${run.eval_run_id}`}>{run.eval_run_id}</Link> : "-"}</td>
                  <td>{formatTimestamp(run.started_at)}</td>
                  <td>{formatTimestamp(run.finished_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
