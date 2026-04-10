import { Link } from "react-router-dom";

import { useMonitorData } from "../app/fetch";
import ErrorState from "../components/ErrorState";

type ThreadsPayload = {
  threads: Array<{
    thread_id: string;
    sandbox?: string | null;
    agent_name?: string | null;
    agent_user_id?: string | null;
    branch_index?: number | null;
    sidebar_label?: string | null;
    avatar_url?: string | null;
    is_main?: boolean | null;
    running?: boolean | null;
    updated_at?: string | null;
  }>;
};

export default function ThreadsPage() {
  const { data, error } = useMonitorData<ThreadsPayload>("/threads");

  if (error) return <ErrorState title="Threads" error={error} />;
  if (!data) return <div>Loading...</div>;

  const threads = data.threads ?? [];
  const runningCount = threads.filter((thread) => thread.running).length;
  const mainCount = threads.filter((thread) => thread.is_main).length;

  return (
    <div className="page">
      <h1>Threads</h1>
      <p className="description">Owner-visible thread truth, trajectory entry points, and runtime linkage.</p>
      <section className="surface-section">
        <h2>Thread Summary</h2>
        <div className="surface-grid">
          <article className="surface-card">
            <p className="surface-card__eyebrow">All Threads</p>
            <p className="surface-card__value">{threads.length}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Running Now</p>
            <p className="surface-card__value">{runningCount}</p>
          </article>
          <article className="surface-card">
            <p className="surface-card__eyebrow">Main Threads</p>
            <p className="surface-card__value">{mainCount}</p>
          </article>
        </div>
      </section>
      <section className="surface-section">
        <div className="leases-workbench-header">
          <div>
            <h2>Thread Workbench</h2>
            <p className="description">Pick a thread to inspect its trajectory, runtime links, and operator truth.</p>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Thread</th>
              <th>Agent</th>
              <th>Sandbox</th>
              <th>Branch</th>
              <th>Status</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {threads.map((thread) => (
              <tr key={thread.thread_id}>
                <td className="mono">
                  <Link to={`/threads/${thread.thread_id}`}>{thread.thread_id}</Link>
                </td>
                <td>{thread.agent_name ?? thread.agent_user_id ?? "-"}</td>
                <td>{thread.sandbox ?? "-"}</td>
                <td>{thread.sidebar_label ?? (thread.branch_index != null ? `Branch ${thread.branch_index}` : "-")}</td>
                <td>{thread.running ? "running" : "idle"}</td>
                <td>{thread.updated_at ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
