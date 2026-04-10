import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type ThreadDetailPayload = {
  thread?: {
    id?: string | null;
    thread_id?: string | null;
    title?: string | null;
    status?: string | null;
  } | null;
  owner?: {
    user_id?: string | null;
    display_name?: string | null;
    email?: string | null;
  } | null;
  summary?: {
    provider_name?: string | null;
    lease_id?: string | null;
    current_instance_id?: string | null;
    desired_state?: string | null;
    observed_state?: string | null;
  } | null;
  sessions?: Array<{
    chat_session_id?: string | null;
    status?: string | null;
  }> | null;
  trajectory?: {
    run_id?: string | null;
    conversation?: Array<{
      role?: string | null;
      text?: string | null;
      tool?: string | null;
      args?: string | null;
    }> | null;
    events?: Array<{
      seq?: number | null;
      event_type?: string | null;
      actor?: string | null;
      summary?: string | null;
    }> | null;
  } | null;
};

function TrajectoryConversation({ items }: { items: NonNullable<NonNullable<ThreadDetailPayload["trajectory"]>["conversation"]> }) {
  if (items.length === 0) {
    return <p className="trajectory-empty">No recorded conversation yet.</p>;
  }

  return (
    <div className="trajectory-ledger">
      {items.map((item, index) => {
        const role = item.role ?? "system";
        return (
          <article key={`${role}-${index}`} className="trajectory-card">
            <div className="trajectory-card__header">
              <span className="trajectory-card__role">{role.replaceAll("_", " ")}</span>
              {item.tool ? <span className="trajectory-card__meta">{item.tool}</span> : null}
            </div>
            {item.args ? (
              <pre className="trajectory-card__detail">{item.args}</pre>
            ) : (
              <p className="trajectory-card__text">{item.text ?? "(empty)"}</p>
            )}
          </article>
        );
      })}
    </div>
  );
}

function TrajectoryEvents({ items }: { items: NonNullable<NonNullable<ThreadDetailPayload["trajectory"]>["events"]> }) {
  if (items.length === 0) {
    return <p className="trajectory-empty">No recorded run events yet.</p>;
  }

  return (
    <div className="trajectory-ledger">
      {items.map((item, index) => (
        <article key={`${item.seq ?? "na"}-${index}`} className="trajectory-card">
          <div className="trajectory-card__header">
            <span className="trajectory-card__role">{item.event_type ?? "event"}</span>
            <span className="trajectory-card__meta">{item.actor ?? "-"}</span>
          </div>
          <p className="trajectory-card__text">{item.summary ?? "-"}</p>
          <p className="trajectory-card__seq">{`#${item.seq ?? "-"}`}</p>
        </article>
      ))}
    </div>
  );
}

export default function ThreadDetailPage() {
  const params = useParams<{ threadId: string }>();
  const threadId = params.threadId ?? "";
  const { data, error } = useMonitorData<ThreadDetailPayload>(`/threads/${threadId}`);
  const [trajectoryView, setTrajectoryView] = useState<"conversation" | "events">("conversation");

  if (error) return <ErrorState title={`Thread ${threadId}`} error={error} />;
  if (!data) return <div>Loading...</div>;

  const summary = data.summary ?? {};
  const owner = data.owner ?? {};
  const trajectory = data.trajectory ?? {};
  const conversation = trajectory.conversation ?? [];
  const events = trajectory.events ?? [];

  return (
    <div className="page">
      <h1>{`Thread ${data.thread?.thread_id ?? threadId}`}</h1>
      <p className="description">
        {data.thread?.title ?? "Operator thread truth"} · {data.thread?.status ?? "-"}
      </p>
      <section className="surface-section">
        <h2>Relations</h2>
        <div className="info-grid">
          <div>
            <strong>Owner</strong>
            <span>{owner.display_name ?? owner.email ?? owner.user_id ?? "-"}</span>
          </div>
          <div>
            <strong>Provider</strong>
            <span>
              {summary.provider_name ? (
                <Link to={`/providers/${summary.provider_name}`}>{summary.provider_name}</Link>
              ) : (
                "-"
              )}
            </span>
          </div>
          <div>
            <strong>Lease</strong>
            <span>
              {summary.lease_id ? <Link to={`/leases/${summary.lease_id}`}>{summary.lease_id}</Link> : "-"}
            </span>
          </div>
          <div>
            <strong>Runtime</strong>
            <span>
              {summary.current_instance_id ? (
                <Link to={`/runtimes/${summary.current_instance_id}`}>{summary.current_instance_id}</Link>
              ) : (
                "-"
              )}
            </span>
          </div>
          <div>
            <strong>Surface</strong>
            <span>
              <Link to="/leases">Leases</Link>
            </span>
          </div>
        </div>
      </section>
      <section className="surface-section">
        <div className="trajectory-header">
          <div>
            <h2>Trajectory</h2>
            <p className="trajectory-subtitle">
              {trajectory.run_id ? `Latest run ${trajectory.run_id}` : "No persisted run selected"}
            </p>
          </div>
          <div className="trajectory-toggle">
            <button
              type="button"
              className={`trajectory-toggle__button ${trajectoryView === "conversation" ? "trajectory-toggle__button--active" : ""}`}
              onClick={() => setTrajectoryView("conversation")}
            >
              Conversation Ledger
            </button>
            <button
              type="button"
              className={`trajectory-toggle__button ${trajectoryView === "events" ? "trajectory-toggle__button--active" : ""}`}
              onClick={() => setTrajectoryView("events")}
            >
              Run Event Timeline
            </button>
          </div>
        </div>
        {trajectoryView === "conversation" ? (
          <TrajectoryConversation items={conversation} />
        ) : (
          <TrajectoryEvents items={events} />
        )}
      </section>
    </div>
  );
}
