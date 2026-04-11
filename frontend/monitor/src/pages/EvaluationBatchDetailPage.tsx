import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
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

export default function EvaluationBatchDetailPage() {
  const params = useParams<{ batchId: string }>();
  const batchId = params.batchId ?? "";
  const { data, error } = useMonitorData<EvaluationBatchDetailPayload>(`/evaluation/batches/${batchId}`);

  if (error) return <ErrorState title={`Evaluation batch ${batchId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const batch = data.batch ?? {};
  const config = batch.config_json ?? {};
  const summary = batch.summary_json ?? {};
  const runs = data.runs ?? [];

  return (
    <div className="page">
      <h1>{`Evaluation Batch ${batch.batch_id ?? batchId}`}</h1>
      <p className="description">Scenario batch truth, run linkage, and thread drilldown.</p>
      <section className="surface-section">
        <h2>Batch Truth</h2>
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
            <strong>Surface</strong>
            <Link to="/evaluation">Evaluation</Link>
          </div>
        </div>
      </section>
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
