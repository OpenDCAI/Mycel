import React from "react";
import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";
import {
  buildArtifactDownloadPayload,
  summarizeTrajectory,
  type EvaluationArtifactRecord,
  type ThreadTrajectoryPayload,
} from "./evaluation-run-detail-model";

type BenchmarkInfo = {
  family?: string | null;
  name?: string | null;
  split?: string | null;
  variant?: string | null;
  instance_id?: string | null;
  dataset_version?: string | null;
  source_uri?: string | null;
};

type JudgeResult = {
  judge_type?: string | null;
  status?: string | null;
  verdict?: string | null;
  rationale?: string | null;
  scores?: Record<string, number> | null;
  metadata?: Record<string, unknown> | null;
};

type EvaluationRunDetailPayload = {
  run?: {
    run_id?: string | null;
    thread_id?: string | null;
    status?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    user_message?: string | null;
    final_response?: string | null;
    artifact_count?: number | null;
    benchmark?: BenchmarkInfo | null;
    judge_result?: JudgeResult | null;
  } | null;
  facts?: Array<{ label?: string | null; value?: string | null }> | null;
  batch_run?: {
    batch_run_id?: string | null;
    batch_id?: string | null;
    scenario_id?: string | null;
  } | null;
  limitations?: string[] | null;
  judge_result?: JudgeResult | null;
  artifacts?: EvaluationArtifactRecord[] | null;
  benchmark?: BenchmarkInfo | null;
};

type EvaluationRunArtifactsPayload = {
  run_id?: string | null;
  artifacts?: EvaluationArtifactRecord[] | null;
  judge_result?: JudgeResult | null;
  benchmark?: BenchmarkInfo | null;
};

type ThreadDetailPayload = {
  trajectory?: ThreadTrajectoryPayload | null;
};

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function stringifyMessage(message: Record<string, unknown>): string {
  if (typeof message.content === "string") return message.content;
  if (typeof message.text === "string") return message.text;
  return JSON.stringify(message, null, 2);
}

function describeMessageRole(message: Record<string, unknown>): string {
  if (typeof message.role === "string") return message.role;
  if (typeof message.actor === "string") return message.actor;
  if (typeof message.type === "string") return message.type;
  return "message";
}

function downloadArtifact(runId: string, artifact: EvaluationArtifactRecord) {
  const payload = buildArtifactDownloadPayload(runId, artifact);
  const blob = new Blob([payload.text], { type: payload.mimeType });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = payload.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export default function EvaluationRunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId ?? "";
  const { data, error } = useMonitorData<EvaluationRunDetailPayload>(`/evaluation/runs/${runId}`);
  const { data: artifactsData, error: artifactsError } =
    useMonitorData<EvaluationRunArtifactsPayload>(`/evaluation/runs/${runId}/artifacts`);
  const threadId = data?.run?.thread_id ?? "";
  const { data: threadData, error: threadError } = useMonitorData<ThreadDetailPayload>(
    threadId ? `/threads/${threadId}` : null,
  );

  if (error) return <ErrorState title={`Evaluation run ${runId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const run = data.run ?? {};
  const facts = data.facts ?? [];
  const batchRun = data.batch_run ?? {};
  const limitations = data.limitations ?? [];
  const judgeResult = artifactsData?.judge_result ?? data.judge_result ?? run.judge_result ?? null;
  const benchmark = artifactsData?.benchmark ?? data.benchmark ?? run.benchmark ?? null;
  const artifacts = artifactsData?.artifacts ?? data.artifacts ?? [];
  const trajectory = threadData?.trajectory ?? null;
  const traceSummary = summarizeTrajectory(trajectory);

  return (
    <div className="page">
      <h1>{`Evaluation Run ${run.run_id ?? runId}`}</h1>
      <p className="description">Persisted evaluation run state, raw thread trace, and artifact viewer.</p>

      <section className="surface-section">
        <h2>Run State</h2>
        <div className="info-grid">
          <div>
            <strong>Thread</strong>
            <span>{run.thread_id || "-"}</span>
          </div>
          <div>
            <strong>Status</strong>
            <span>{run.status ?? "-"}</span>
          </div>
          <div>
            <strong>Started At</strong>
            <span>{formatTimestamp(run.started_at)}</span>
          </div>
          <div>
            <strong>Finished At</strong>
            <span>{formatTimestamp(run.finished_at)}</span>
          </div>
          <div>
            <strong>User Message</strong>
            <span>{run.user_message ?? "-"}</span>
          </div>
          <div>
            <strong>Batch</strong>
            {batchRun.batch_id ? <Link to={`/evaluation/batches/${batchRun.batch_id}`}>{batchRun.batch_id}</Link> : <span>-</span>}
          </div>
          <div>
            <strong>Scenario</strong>
            <span>{batchRun.scenario_id ?? "-"}</span>
          </div>
          <div>
            <strong>Surface</strong>
            <Link to="/evaluation">Evaluation</Link>
          </div>
        </div>
      </section>

      <section className="surface-section">
        <h2>Benchmark & Judge</h2>
        <div className="info-grid">
          <div>
            <strong>Family</strong>
            <span>{benchmark?.family ?? "-"}</span>
          </div>
          <div>
            <strong>Name</strong>
            <span>{benchmark?.name ?? "-"}</span>
          </div>
          <div>
            <strong>Split</strong>
            <span>{benchmark?.split ?? "-"}</span>
          </div>
          <div>
            <strong>Instance</strong>
            <span className="mono">{benchmark?.instance_id ?? "-"}</span>
          </div>
          <div>
            <strong>Judge Type</strong>
            <span>{judgeResult?.judge_type ?? "-"}</span>
          </div>
          <div>
            <strong>Judge Status</strong>
            <span>{judgeResult?.status ?? "-"}</span>
          </div>
          <div>
            <strong>Judge Verdict</strong>
            <span>{judgeResult?.verdict ?? "-"}</span>
          </div>
          <div>
            <strong>Artifact Count</strong>
            <span>{artifacts.length}</span>
          </div>
        </div>
        {judgeResult?.rationale ? <p className="description">{judgeResult.rationale}</p> : null}
        {judgeResult?.scores && Object.keys(judgeResult.scores).length > 0 ? (
          <div className="info-grid">
            {Object.entries(judgeResult.scores).map(([key, value]) => (
              <div key={key}>
                <strong>{key}</strong>
                <span>{value}</span>
              </div>
            ))}
          </div>
        ) : null}
        {run.final_response ? (
          <details className="evaluation-json-panel">
            <summary>Final response</summary>
            <pre>{run.final_response}</pre>
          </details>
        ) : null}
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

      <section className="surface-section">
        <h2>Artifact Viewer</h2>
        {artifactsError ? <p className="description error">{artifactsError.message}</p> : null}
        {artifacts.length > 0 ? (
          <div className="evaluation-artifact-grid">
            {artifacts.map((artifact, index) => (
              <article key={`${artifact.name ?? artifact.path ?? artifact.kind}-${index}`} className="surface-card">
                <div className="evaluation-artifact-card__header">
                  <div>
                    <p className="surface-card__eyebrow">{artifact.kind ?? "artifact"}</p>
                    <h3 className="evaluation-artifact-card__title mono">{artifact.name ?? artifact.path ?? "-"}</h3>
                  </div>
                  <button
                    type="button"
                    className="monitor-action-button"
                    onClick={() => downloadArtifact(runId, artifact)}
                  >
                    Download
                  </button>
                </div>
                <div className="info-grid">
                  <div>
                    <strong>Mime</strong>
                    <span>{artifact.mime_type ?? "-"}</span>
                  </div>
                  <div>
                    <strong>Path</strong>
                    <span className="mono">{artifact.path ?? "-"}</span>
                  </div>
                </div>
                <details className="evaluation-json-panel">
                  <summary>Metadata</summary>
                  <pre>{JSON.stringify(artifact.metadata ?? {}, null, 2)}</pre>
                </details>
                <details className="evaluation-json-panel">
                  <summary>Payload preview</summary>
                  <pre>{artifact.content ?? JSON.stringify(artifact, null, 2)}</pre>
                </details>
              </article>
            ))}
          </div>
        ) : (
          <article className="surface-card">
            <p className="surface-card__body">Artifacts API returned no artifacts for this run.</p>
          </article>
        )}
      </section>

      <section className="surface-section">
        <h2>Raw Trace</h2>
        {threadError ? <p className="description error">{threadError.message}</p> : null}
        {!threadId ? <p className="description">This evaluation run is not linked to a persisted thread yet.</p> : null}
        {threadId && !traceSummary.hasTrace && !threadError ? (
          <p className="description">Thread detail loaded, but it exposed no conversation or event trace.</p>
        ) : null}
        {traceSummary.hasTrace ? (
          <div className="evaluation-trace-grid">
            <article className="surface-card">
              <div className="evaluation-contract-preview__header">
                <strong>Conversation</strong>
                <span>{traceSummary.messageCount} messages</span>
              </div>
              {trajectory?.conversation?.map((message, index) => (
                <details key={`${String(message.role ?? message.actor ?? index)}-${index}`} className="evaluation-json-panel">
                  <summary>
                    {index + 1}. {describeMessageRole(message)}
                  </summary>
                  <pre>{stringifyMessage(message)}</pre>
                </details>
              ))}
            </article>
            <article className="surface-card">
              <div className="evaluation-contract-preview__header">
                <strong>Events</strong>
                <span>{traceSummary.eventCount} events</span>
              </div>
              {trajectory?.events?.map((event, index) => (
                <details
                  key={`${event.seq ?? index}-${event.event_type ?? "event"}`}
                  className="evaluation-json-panel"
                >
                  <summary>
                    {event.seq ?? index + 1}. {event.actor ?? "-"} / {event.event_type ?? "-"} / {event.summary ?? "-"}
                  </summary>
                  <pre>{JSON.stringify(event.payload ?? {}, null, 2)}</pre>
                </details>
              ))}
            </article>
          </div>
        ) : null}
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
