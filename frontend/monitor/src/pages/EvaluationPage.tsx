import { Link } from "react-router-dom";

import ErrorState from "../components/ErrorState";
import { useMonitorData } from "../app/fetch";

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

export default function EvaluationPage() {
  const { data, error } = useMonitorData<EvaluationPayload>("/evaluation");
  const { data: batchesData, error: batchesError } = useMonitorData<EvaluationBatchIndexPayload>("/evaluation/batches");
  const { data: scenariosData, error: scenariosError } =
    useMonitorData<EvaluationScenarioCatalogPayload>("/evaluation/scenarios");

  if (error) return <ErrorState title="Evaluation" error={error} />;
  if (batchesError) return <ErrorState title="Evaluation batches" error={batchesError} />;
  if (scenariosError) return <ErrorState title="Evaluation scenarios" error={scenariosError} />;
  if (!data || !batchesData || !scenariosData) return <div>Loading...</div>;

  const overview = data.overview ?? {};
  const runs = data.runs ?? [];
  const selectedRun = data.selected_run ?? {};
  const facts = selectedRun.facts ?? [];
  const limitations = data.limitations ?? [];
  const batches = batchesData.items ?? [];
  const scenarios = scenariosData.items ?? [];

  return (
    <div className="page">
      <h1>Evaluation</h1>
      <p className="description">{data.headline ?? "Evaluation workbench truth."}</p>
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
        <h2>Scenario Catalog</h2>
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Name</th>
              <th>Category</th>
              <th>Sandbox</th>
              <th>Messages</th>
              <th>Timeout</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.length > 0 ? (
              scenarios.map((scenario) => (
                <tr key={scenario.scenario_id ?? scenario.name}>
                  <td className="mono">
                    {scenario.scenario_id ? (
                      <Link to={`/evaluation?scenario=${scenario.scenario_id}`}>{scenario.scenario_id}</Link>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>{scenario.name ?? "-"}</td>
                  <td>{scenario.category ?? "-"}</td>
                  <td>{scenario.sandbox ?? "-"}</td>
                  <td>{scenario.message_count ?? 0}</td>
                  <td>{scenario.timeout_seconds ?? "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6}>No evaluation scenarios found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
      <section className="surface-section">
        <h2>Batch Queue</h2>
        <table>
          <thead>
            <tr>
              <th>Batch</th>
              <th>Status</th>
              <th>Runs</th>
              <th>Agent</th>
              <th>Submitted By</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {batches.length > 0 ? (
              batches.map((batch) => {
                const summary = batch.summary_json ?? {};
                const summaryText = `${summary.total_runs ?? 0} total / ${summary.running_runs ?? 0} running / ${
                  summary.completed_runs ?? 0
                } completed / ${summary.failed_runs ?? 0} failed`;
                return (
                  <tr key={batch.batch_id ?? `${batch.kind}-${batch.created_at}`}>
                    <td className="mono">
                      {batch.batch_id ? <Link to={`/evaluation/batches/${batch.batch_id}`}>{batch.batch_id}</Link> : "-"}
                    </td>
                    <td>{batch.status ?? "-"}</td>
                    <td>{summaryText}</td>
                    <td>{batch.agent_user_id ?? "-"}</td>
                    <td>{batch.submitted_by_user_id ?? "-"}</td>
                    <td>{batch.created_at ?? "-"}</td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={6}>No evaluation batches yet.</td>
              </tr>
            )}
          </tbody>
        </table>
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
          <h2>Workbench Boundary</h2>
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
