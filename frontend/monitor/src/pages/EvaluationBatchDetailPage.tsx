import React from "react";
import { Link, useParams } from "react-router-dom";

import { postMonitorData, useMonitorData, type MonitorFetchError } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type EvaluationBatchDetailPayload = {
  batch?: {
    batch_id?: string | null;
    kind?: string | null;
    status?: string | null;
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
  } | null;
  runs?: Array<{
    batch_run_id?: string | null;
    scenario_id?: string | null;
    status?: string | null;
    thread_id?: string | null;
    eval_run_id?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
  }> | null;
};

type EvaluationBatchStartPayload = {
  accepted: boolean;
  batch?: EvaluationBatchDetailPayload["batch"];
};

export default function EvaluationBatchDetailPage() {
  const params = useParams<{ batchId: string }>();
  const batchId = params.batchId ?? "";
  const { data, error } = useMonitorData<EvaluationBatchDetailPayload>(`/evaluation/batches/${batchId}`);
  const [batchData, setBatchData] = React.useState<EvaluationBatchDetailPayload | null>(null);
  const [startMessage, setStartMessage] = React.useState<string | null>(null);
  const [startError, setStartError] = React.useState<string | null>(null);
  const [startPending, setStartPending] = React.useState(false);

  React.useEffect(() => {
    if (data) {
      setBatchData(data);
      setStartMessage(null);
      setStartError(null);
      setStartPending(false);
    }
  }, [data]);

  if (error) return <ErrorState title={`Evaluation batch ${batchId}`} error={error} />;
  if (!batchData) return <div>Loading...</div>;

  const batch = batchData.batch ?? {};
  const config = batch.config_json ?? {};
  const summary = batch.summary_json ?? {};
  const runs = batchData.runs ?? [];
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

  return (
    <div className="page">
      <h1>{`Evaluation Batch ${batch.batch_id ?? batchId}`}</h1>
      <p className="description">Scenario batch state, run linkage, and thread drilldown.</p>
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
          {startError ? <p className="description">{startError}</p> : null}
        </section>
      ) : null}
      <section className="surface-section">
        <h2>Batch Runs</h2>
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Status</th>
              <th>Thread</th>
              <th>Eval Run</th>
              <th>Started</th>
              <th>Finished</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.batch_run_id ?? run.scenario_id}>
                <td className="mono">{run.scenario_id ?? "-"}</td>
                <td>{run.status ?? "-"}</td>
                <td>{run.thread_id ? <Link to={`/threads/${run.thread_id}`}>{run.thread_id}</Link> : "-"}</td>
                <td>{run.eval_run_id ? <Link to={`/evaluation/runs/${run.eval_run_id}`}>{run.eval_run_id}</Link> : "-"}</td>
                <td>{run.started_at ?? "-"}</td>
                <td>{run.finished_at ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
