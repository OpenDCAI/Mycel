import React from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Link,
  NavLink,
  Navigate,
  useLocation,
  useParams,
} from "react-router-dom";
import "./styles.css";

const API_BASE = "/api/monitor";

// Utility: Fetch JSON from API
async function fetchAPI(path: string) {
  const res = await fetch(`${API_BASE}${path}`);
  const text = await res.text();
  let payload: any = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(
      `Invalid JSON from ${path} (${res.status}): ${text.slice(0, 180)}`,
    );
  }
  if (!res.ok) {
    throw new Error(payload?.detail || `${res.status} ${res.statusText}`);
  }
  return payload;
}

async function fetchJSON(path: string, init?: RequestInit) {
  const res = await fetch(path, init);
  const text = await res.text();
  let payload: any = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(
      `Invalid JSON from ${path} (${res.status}): ${text.slice(0, 180)}`,
    );
  }
  if (!res.ok) {
    throw new Error(payload?.detail || `${res.status} ${res.statusText}`);
  }
  return payload;
}

// Component: Breadcrumb navigation
function Breadcrumb({
  items,
}: {
  items: Array<{ label: string; url: string }>;
}) {
  return (
    <div className="breadcrumb">
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span> / </span>}
          <Link to={item.url}>{item.label}</Link>
        </React.Fragment>
      ))}
    </div>
  );
}

// Component: State badge
function StateBadge({ badge }: { badge: any }) {
  const className = `state-badge state-${badge.color}`;
  const text = badge.text || badge.observed;
  const tooltip = badge.hours_diverged
    ? `Diverged for ${badge.hours_diverged}h`
    : badge.converged
      ? "Converged"
      : `${badge.observed} → ${badge.desired}`;

  return (
    <span className={className} title={tooltip}>
      {text}
    </span>
  );
}

function DashboardMetric({
  label,
  value,
  note,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
  tone?: "default" | "warning" | "danger" | "success";
}) {
  return (
    <div className={`dashboard-metric dashboard-metric-${tone}`}>
      <span className="dashboard-metric-label">{label}</span>
      <strong className="dashboard-metric-value">{value}</strong>
      {note ? <span className="dashboard-metric-note">{note}</span> : null}
    </div>
  );
}

function evaluationStatusTone(item: any): string {
  const status = String(item?.status || "").toLowerCase();
  const publishable = Boolean(
    item?.score?.publishable ?? item?.score?.score_gate === "final",
  );
  if (status === "error" || status === "completed_with_errors") {
    return "chip-danger";
  }
  if (publishable) return "chip-success";
  if (status === "provisional" || status === "running" || status === "queued") {
    return "chip-warning";
  }
  return "chip-muted";
}

function evaluationScoreTone(item: any): string {
  const publishable = Boolean(
    item?.score?.publishable ?? item?.score?.score_gate === "final",
  );
  return publishable ? "chip-success" : "chip-warning";
}

function DashboardPage() {
  const [data, setData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadDashboard = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchAPI("/dashboard");
      setData(payload);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  if (error) {
    return (
      <div className="page" data-testid="page-dashboard">
        <div className="page-error">Dashboard load failed: {error}</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page" data-testid="page-dashboard">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }

  const infra = data.infra || {};
  const workload = data.workload || {};
  const latestEval = data.latest_evaluation || null;
  const resourcesSummary = data.resources_summary || {};

  return (
    <div className="page" data-testid="page-dashboard">
      <section className="dashboard-grid">
        <article className="depth-primary dashboard-card dashboard-card-hero">
          <div className="section-row dashboard-card-head">
            <h2>Infra Health</h2>
            <div className="console-header-actions">
              <button className="ghost-btn" onClick={() => void loadDashboard()} disabled={loading}>
                {loading ? "Refreshing..." : "Refresh"}
              </button>
              <Link className="quick-link" to="/resources">Resources</Link>
            </div>
          </div>
          <div className="dashboard-metric-grid">
            <DashboardMetric
              label="Providers"
              value={`${resourcesSummary.active_providers || 0}/${resourcesSummary.total_providers || 0}`}
              note={`${resourcesSummary.unavailable_providers || 0} unavailable`}
              tone={
                (resourcesSummary.unavailable_providers || 0) > 0
                  ? "warning"
                  : "success"
              }
            />
            <DashboardMetric
              label="Diverged leases"
              value={
                <Link
                  className="dashboard-inline-link"
                  to="/resources#lease-health"
                >
                  {infra.leases_diverged || 0}
                </Link>
              }
              note={`${infra.leases_total || 0} total`}
              tone={(infra.leases_diverged || 0) > 0 ? "warning" : "success"}
            />
            <DashboardMetric
              label="Orphans"
              value={
                <Link
                  className="dashboard-inline-link"
                  to="/resources#lease-health"
                >
                  {infra.leases_orphan || 0}
                </Link>
              }
              note={`${infra.leases_healthy || 0} healthy`}
              tone={(infra.leases_orphan || 0) > 0 ? "danger" : "success"}
            />
          </div>
        </article>

        <div className="dashboard-sidebar-stack">
          <article className="depth-secondary dashboard-card">
            <div className="section-row dashboard-card-head">
              <h2>Active Workload</h2>
              <Link className="quick-link" to="/threads">
                Threads
              </Link>
            </div>
            <div className="dashboard-metric-grid">
              <DashboardMetric
                label="DB sessions"
                value={workload.db_sessions_total || 0}
                note="durable chat sessions"
              />
              <DashboardMetric
                label="Provider sessions"
                value={workload.provider_sessions_total || 0}
                note="reported by providers"
              />
              <DashboardMetric
                label="Running"
                value={workload.running_sessions || 0}
                note={`${workload.evaluations_running || 0} eval jobs`}
                tone={
                  (workload.running_sessions || 0) > 0 ? "default" : "warning"
                }
              />
            </div>
          </article>

          <article className="depth-secondary dashboard-card dashboard-card-eval">
            <div className="section-row dashboard-card-head">
              <h2>Latest Eval</h2>
              <Link
                className="quick-link"
                to={latestEval?.evaluation_url || "/evaluation"}
              >
                {latestEval ? "Detail" : "Eval list"}
              </Link>
            </div>
            {latestEval ? (
              <div className="dashboard-eval-body">
                <div className="chip-row">
                  <span
                    className={`status-chip ${latestEval.status === "provisional" ? "chip-warning" : latestEval.status === "error" ? "chip-danger" : "chip-muted"}`}
                  >
                    {latestEval.status}
                  </span>
                  <span
                    className={`status-chip ${latestEval.publishable ? "chip-success" : "chip-warning"}`}
                  >
                    publishable={String(Boolean(latestEval.publishable))}
                  </span>
                </div>
                <div className="eval-progress-track">
                  <div
                    className="eval-progress-fill"
                    style={{ width: `${Number(latestEval.progress_pct || 0)}%` }}
                  />
                </div>
                <div className="mono eval-progress-line">
                  {latestEval.threads_done || 0}/{latestEval.threads_total || 0}{" "}
                  threads · {formatPct(latestEval.progress_pct || 0)} · updated{" "}
                  {latestEval.updated_ago || "-"}
                </div>
                <DashboardMetric
                  label="Primary score"
                  value={
                    latestEval.primary_score_pct == null
                      ? "provisional"
                      : formatPct(latestEval.primary_score_pct)
                  }
                  tone={
                    latestEval.primary_score_pct == null ? "warning" : "success"
                  }
                />
              </div>
            ) : (
              <p className="count">No evaluations yet</p>
            )}
          </article>
        </div>
      </section>
    </div>
  );
}

const CAPABILITY_LABELS: Record<string, string> = {
  filesystem: "FS",
  terminal: "TERM",
  metrics: "METRICS",
  screenshot: "SHOT",
  web: "WEB",
  process: "PROC",
  hooks: "HOOKS",
  mount: "MOUNT",
};

function formatMonitorMetric(value: any, suffix = "", digits = 1): string {
  if (value == null) return "--";
  const num = Number(value);
  if (!Number.isFinite(num)) return "--";
  return `${num.toFixed(digits)}${suffix}`;
}

function ProviderStatusLight({ status }: { status: string }) {
  const className =
    status === "active"
      ? "provider-status-light is-active"
      : status === "ready"
        ? "provider-status-light is-ready"
        : "provider-status-light is-unavailable";
  return <span className={className} aria-hidden="true" />;
}

function ProviderMiniMetric({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
}) {
  return (
    <div className="provider-mini-metric">
      <span className="provider-mini-label">{label}</span>
      <strong className="provider-mini-value">{value}</strong>
      {note ? <span className="provider-mini-note">{note}</span> : null}
    </div>
  );
}

function CapabilityStrip({
  capabilities,
}: {
  capabilities: Record<string, boolean> | null | undefined;
}) {
  const enabled = Object.entries(capabilities || {}).filter(([, value]) =>
    Boolean(value),
  );
  if (enabled.length === 0) {
    return (
      <div className="provider-capability-strip">
        <span className="provider-capability-chip is-muted">
          No capabilities
        </span>
      </div>
    );
  }
  return (
    <div className="provider-capability-strip">
      {enabled.slice(0, 5).map(([name]) => (
        <span key={name} className="provider-capability-chip">
          {CAPABILITY_LABELS[name] || name}
        </span>
      ))}
    </div>
  );
}

function SessionDotStrip({ sessions }: { sessions: any[] }) {
  if (!sessions.length) {
    return (
      <div className="provider-session-strip provider-session-empty">
        No active or historical sessions
      </div>
    );
  }
  const sorted = [...sessions].sort((a, b) => {
    const order = {
      running: 0,
      destroying: 1,
      paused: 2,
      stopped: 3,
    } as Record<string, number>;
    return (order[a.status] ?? 4) - (order[b.status] ?? 4);
  });
  const running = sessions.filter(
    (session) => session.status === "running",
  ).length;
  const paused = sessions.filter(
    (session) => session.status === "paused",
  ).length;
  const stopped = sessions.filter(
    (session) => session.status === "stopped",
  ).length;
  return (
    <div className="provider-session-strip">
      <div className="provider-session-dots">
        {sorted.slice(0, 6).map((session) => (
          <span
            key={session.id}
            className={`provider-session-dot status-${session.status || "unknown"}`}
            title={`${session.id} · ${session.status}`}
          />
        ))}
      </div>
      <span className="provider-session-copy">
        {running} running
        {paused ? ` · ${paused} paused` : ""}
        {stopped ? ` · ${stopped} stopped` : ""}
      </span>
    </div>
  );
}

function groupSessionsByLease(sessions: any[]) {
  const statusOrder: Record<string, number> = {
    running: 0,
    destroying: 1,
    paused: 2,
    stopped: 3,
  };
  const groups = new Map<string, any[]>();
  for (const session of sessions) {
    const key = session.leaseId || session.id;
    const bucket = groups.get(key) || [];
    bucket.push(session);
    groups.set(key, bucket);
  }
  return Array.from(groups.values())
    .map((group) => {
      const sorted = [...group].sort(
        (a, b) => (statusOrder[a.status] ?? 4) - (statusOrder[b.status] ?? 4),
      );
      const lead = sorted[0];
      return {
        leaseId: lead.leaseId || lead.id,
        status: lead.status,
        sessions: sorted,
        threadId: lead.threadId || null,
        memberName: lead.memberName || lead.memberId || "未绑定Agent",
        startedAt: sorted.reduce(
          (min, item) => (item.startedAt < min ? item.startedAt : min),
          sorted[0].startedAt,
        ),
      };
    })
    .sort(
      (a, b) => (statusOrder[a.status] ?? 4) - (statusOrder[b.status] ?? 4),
    );
}

function leaseGroupKey(group: any) {
  return String(
    group.leaseId || group.threadId || group.startedAt || "lease-group",
  );
}

function ProviderLeaseCard({
  group,
  selected,
  onSelect,
}: {
  group: any;
  selected: boolean;
  onSelect: () => void;
}) {
  const running = group.sessions.filter(
    (session: any) => session.status === "running",
  ).length;
  const paused = group.sessions.filter(
    (session: any) => session.status === "paused",
  ).length;
  const stopped = group.sessions.filter(
    (session: any) => session.status === "stopped",
  ).length;
  const toneClass =
    group.status === "running"
      ? "status-running"
      : group.status === "paused"
        ? "status-paused"
        : group.status === "destroying"
          ? "status-destroying"
          : "status-stopped";
  return (
    <article
      className={`provider-lease-card${selected ? " is-selected" : ""}`}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      data-lease-group-id={leaseGroupKey(group)}
      role="button"
      tabIndex={0}
    >
      <div className="provider-lease-header">
        <div>
          {group.leaseId ? (
            <Link
              className="provider-lease-link"
              to={`/lease/${group.leaseId}`}
            >
              {shortId(group.leaseId, 12)}
            </Link>
          ) : (
            <strong className="provider-lease-link">ephemeral</strong>
          )}
          <p>
            {group.threadId ? shortId(group.threadId, 14) : "no thread binding"}
          </p>
        </div>
        <span className={`status-chip ${toneClass}`}>{group.status}</span>
      </div>
      <div className="provider-lease-meta">
        <span>
          <strong>Member</strong>
          {group.memberName}
        </span>
        <span>
          <strong>Started</strong>
          {new Date(group.startedAt).toLocaleString()}
        </span>
      </div>
      <div className="resource-overview-strip provider-lease-strip">
        <span className="resource-overview-pill">
          <span className="resource-overview-label">sessions</span>
          <strong>{group.sessions.length}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">running</span>
          <strong>{running}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">paused</span>
          <strong>{paused}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">stopped</span>
          <strong>{stopped}</strong>
        </span>
      </div>
    </article>
  );
}

function MonitorLeaseDetailPanel({ group }: { group: any }) {
  const running = group.sessions.filter(
    (session: any) => session.status === "running",
  ).length;
  const paused = group.sessions.filter(
    (session: any) => session.status === "paused",
  ).length;
  const stopped = group.sessions.filter(
    (session: any) => session.status === "stopped",
  ).length;

  return (
    <section
      className="monitor-lease-detail-shell"
      data-testid="monitor-lease-detail"
    >
      <div className="section-row">
        <div>
          <div className="provider-detail-heading">
            <h2>Lease Detail</h2>
            <span className="mono monitor-lease-detail-id">
              {group.leaseId || "ephemeral"}
            </span>
          </div>
        </div>
        <div className="provider-detail-actions">
          {group.leaseId ? (
            <Link className="quick-link" to={`/lease/${group.leaseId}`}>
              Open lease
            </Link>
          ) : null}
          {group.threadId ? (
            <Link className="quick-link" to={`/thread/${group.threadId}`}>
              Open thread
            </Link>
          ) : null}
        </div>
      </div>
      <div className="resource-overview-strip">
        <span className="resource-overview-pill">
          <span className="resource-overview-label">sessions</span>
          <strong>{group.sessions.length}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">running</span>
          <strong>{running}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">paused</span>
          <strong>{paused}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">stopped</span>
          <strong>{stopped}</strong>
        </span>
      </div>
      <div className="monitor-lease-context-bar">
        <div className="monitor-lease-context-item">
          <strong>Member</strong>
          <span>{group.memberName}</span>
        </div>
        <div className="monitor-lease-context-item">
          <strong>Thread</strong>
          <span>
            {group.threadId ? shortId(group.threadId, 14) : "no thread binding"}
          </span>
        </div>
        <div className="monitor-lease-context-item">
          <strong>Started</strong>
          <span>
            {group.startedAt
              ? new Date(group.startedAt).toLocaleString()
              : "--"}
          </span>
        </div>
        <div className="monitor-lease-context-item">
          <strong>Status</strong>
          <span>{group.status}</span>
        </div>
      </div>
      <table className="monitor-lease-session-table resource-table-dense">
        <thead>
          <tr>
            <th>Session</th>
            <th>Member</th>
            <th>Thread</th>
            <th>Status</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>
          {group.sessions.map((session: any) => (
            <tr key={session.id}>
              <td>
                <Link to={`/session/${session.id}`}>
                  {shortId(session.id, 12)}
                </Link>
              </td>
              <td>{session.memberName || session.memberId || "-"}</td>
              <td>
                {session.threadId ? (
                  <Link to={`/thread/${session.threadId}`}>
                    {shortId(session.threadId, 12)}
                  </Link>
                ) : (
                  "-"
                )}
              </td>
              <td>{session.status}</td>
              <td>
                {session.startedAt
                  ? new Date(session.startedAt).toLocaleString()
                  : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function MonitorResourcesPage() {
  const [resourceData, setResourceData] = React.useState<any>(null);
  const [leaseData, setLeaseData] = React.useState<any>(null);
  const [selectedId, setSelectedId] = React.useState("");
  const [selectedLeaseId, setSelectedLeaseId] = React.useState("");
  const [sessionScope, setSessionScope] = React.useState<"lease" | "provider">(
    "lease",
  );
  const [loading, setLoading] = React.useState(false);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadResources = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [resources, leases] = await Promise.all([
        fetchAPI("/resources"),
        fetchAPI("/leases"),
      ]);
      setResourceData(resources);
      setLeaseData(leases);
      const providers = Array.isArray(resources?.providers)
        ? resources.providers
        : [];
      setSelectedId((prev) =>
        providers.some((provider: any) => provider.id === prev)
          ? prev
          : providers[0]?.id || "",
      );
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshNow = React.useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [resources, leases] = await Promise.all([
        fetchJSON(`${API_BASE}/resources/refresh`, { method: "POST" }),
        fetchAPI("/leases"),
      ]);
      setResourceData(resources);
      setLeaseData(leases);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setRefreshing(false);
    }
  }, []);

  React.useEffect(() => {
    void loadResources();
  }, [loadResources]);

  React.useEffect(() => {
    if (!resourceData || !leaseData) {
      setSelectedLeaseId("");
      return;
    }
    const providers = Array.isArray(resourceData.providers)
      ? resourceData.providers
      : [];
    const selectedProvider =
      providers.find((provider: any) => provider.id === selectedId) ||
      providers[0] ||
      null;
    const selectedSessions = Array.isArray(selectedProvider?.sessions)
      ? selectedProvider.sessions
      : [];
    const nextLeaseGroups = groupSessionsByLease(selectedSessions);
    setSelectedLeaseId((prev) => {
      if (nextLeaseGroups.some((group: any) => leaseGroupKey(group) === prev)) {
        return prev;
      }
      return nextLeaseGroups[0] ? leaseGroupKey(nextLeaseGroups[0]) : "";
    });
  }, [leaseData, resourceData, selectedId]);

  React.useEffect(() => {
    setSessionScope("lease");
  }, [selectedId, selectedLeaseId]);

  if (error) {
    return (
      <div className="page" data-testid="page-resources">
        <div className="page-error">Resource load failed: {error}</div>
      </div>
    );
  }

  if (!resourceData || !leaseData) {
    return (
      <div className="page" data-testid="page-resources">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }

  const providers = Array.isArray(resourceData.providers)
    ? resourceData.providers
    : [];
  const summary = resourceData.summary || {};
  const leases = Array.isArray(leaseData.items) ? leaseData.items : [];
  const leaseTriage = leaseData.triage || {};
  const triageSummary = leaseTriage.summary || {};
  const triageGroups = Array.isArray(leaseTriage.groups)
    ? leaseTriage.groups
    : [];
  const selectedProvider =
    providers.find((provider: any) => provider.id === selectedId) ||
    providers[0] ||
    null;
  const activeDriftLeases = (triageGroups.find(
    (group: any) => group.key === "active_drift",
  )?.items || []) as any[];
  const detachedResidueLeases = (triageGroups.find(
    (group: any) => group.key === "detached_residue",
  )?.items || []) as any[];
  const orphanCleanupLeases = (triageGroups.find(
    (group: any) => group.key === "orphan_cleanup",
  )?.items || []) as any[];
  const healthyCapacityLeases = (triageGroups.find(
    (group: any) => group.key === "healthy_capacity",
  )?.items || []) as any[];
  const hasPrimaryLeaseAttention =
    activeDriftLeases.length > 0 || detachedResidueLeases.length > 0;
  const hasSecondaryLeaseAttention = orphanCleanupLeases.length > 0;
  const refreshedAt = summary.last_refreshed_at || summary.snapshot_at;
  const selectedSessions = Array.isArray(selectedProvider?.sessions)
    ? selectedProvider.sessions
    : [];
  const selectedLeaseGroups = groupSessionsByLease(selectedSessions);
  const selectedRunning = selectedSessions.filter(
    (session: any) => session.status === "running",
  ).length;
  const selectedPaused = selectedSessions.filter(
    (session: any) => session.status === "paused",
  ).length;
  const selectedStopped = selectedSessions.filter(
    (session: any) => session.status === "stopped",
  ).length;
  const selectedLeaseGroup =
    selectedLeaseGroups.find(
      (group: any) => leaseGroupKey(group) === selectedLeaseId,
    ) ||
    selectedLeaseGroups[0] ||
    null;
  const scopedSessions =
    sessionScope === "provider" || !selectedLeaseGroup
      ? selectedSessions
      : selectedLeaseGroup.sessions;

  return (
    <div className="page" data-testid="page-resources">
      <div className="sticky-context">
        <div className="resource-summary-grid">
        <DashboardMetric
          label="Providers"
          value={summary.total_providers || 0}
          note={`${summary.active_providers || 0} active · ${summary.unavailable_providers || 0} unavailable`}
        />
        <DashboardMetric
          label="Running sessions"
          value={summary.running_sessions || 0}
          note={
            refreshedAt
              ? `refreshed ${new Date(refreshedAt).toLocaleTimeString()}`
              : "no timestamp"
          }
        />
        <DashboardMetric
          label="Active drift"
          value={triageSummary.active_drift || 0}
          note="needs operator attention"
          tone={(triageSummary.active_drift || 0) > 0 ? "warning" : "success"}
        />
        <DashboardMetric
          label="Detached residue"
          value={triageSummary.detached_residue || 0}
          note={`${triageSummary.orphan_cleanup || 0} cleanup backlog`}
          tone={
            (triageSummary.detached_residue || 0) > 0 ? "danger" : "success"
          }
        />
        <DashboardMetric
          label="Healthy leases"
          value={triageSummary.healthy_capacity || 0}
          note={`${triageSummary.total || leases.length} total`}
          tone={
            (triageSummary.healthy_capacity || 0) > 0 ? "success" : "danger"
          }
        />
        </div>
      </div>

      <section className="resource-split-console">
        <div className="resource-rail">
          <div className="section-row">
            <h2>Providers</h2>
            <button className="ghost-btn" onClick={() => void refreshNow()} disabled={refreshing || loading}>
              {refreshing ? "..." : "Refresh"}
            </button>
          </div>
          <div className="resource-rail-list">
            {providers.map((provider: any) => {
              const sessions = Array.isArray(provider.sessions) ? provider.sessions : [];
              const runningCount = sessions.filter((s: any) => s.status === "running").length;
              const unavailable = provider.status === "unavailable";
              return (
                <button
                  key={provider.id}
                  type="button"
                  className={`resource-rail-item${provider.id === selectedId ? " is-selected" : ""}${unavailable ? " is-unavailable" : ""}`}
                  onClick={() => setSelectedId(provider.id)}
                  data-provider-id={provider.id}
                >
                  <div className="resource-rail-row">
                    <ProviderStatusLight status={provider.status} />
                    <strong>{provider.name}</strong>
                  </div>
                  <div className="resource-rail-meta">
                    <span>{provider.type}</span>
                    <span>{sessions.length} sess · {runningCount} run</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
        <div className="resource-detail">
          {selectedProvider ? (
          <>
          <div className="provider-detail-shell">
            <div className="section-row">
              <div>
                <div className="provider-detail-heading">
                  <ProviderStatusLight status={selectedProvider.status} />
                  <h2>{selectedProvider.name}</h2>
                </div>
                <p className="description">
                  {selectedProvider.description || "No provider description."}
                </p>
              </div>
              <div className="provider-detail-actions">
                <span
                  className={`status-chip ${selectedProvider.status === "active" ? "chip-success" : selectedProvider.status === "unavailable" ? "chip-danger" : "chip-muted"}`}
                >
                  {selectedProvider.type}
                  {selectedProvider.vendor
                    ? ` · ${selectedProvider.vendor}`
                    : ""}
                </span>
                {selectedProvider.consoleUrl ? (
                  <a
                    className="quick-link"
                    href={selectedProvider.consoleUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open console
                  </a>
                ) : null}
              </div>
            </div>
            <div className="resource-overview-strip">
              <span className="resource-overview-pill">
                <span className="resource-overview-label">status</span>
                <strong>{selectedProvider.status}</strong>
              </span>
              <span className="resource-overview-pill">
                <span className="resource-overview-label">running</span>
                <strong>{selectedRunning}</strong>
              </span>
              <span className="resource-overview-pill">
                <span className="resource-overview-label">paused</span>
                <strong>{selectedPaused}</strong>
              </span>
              <span className="resource-overview-pill">
                <span className="resource-overview-label">stopped</span>
                <strong>{selectedStopped}</strong>
              </span>
            </div>
            <CapabilityStrip capabilities={selectedProvider.capabilities} />
            <div className="info-grid info-grid-compact">
              <div>
                <strong>Provider</strong>
                <span>
                  {selectedProvider.type}
                  {selectedProvider.vendor
                    ? ` · ${selectedProvider.vendor}`
                    : ""}
                </span>
              </div>
              <div>
                <strong>CPU</strong>
                <span>
                  {selectedProvider.telemetry?.cpu?.used == null
                    ? "--"
                    : `${Number(selectedProvider.telemetry.cpu.used).toFixed(1)}%`}
                </span>
              </div>
              <div>
                <strong>Memory</strong>
                <span>
                  {selectedProvider.telemetry?.memory?.used == null
                    ? "--"
                    : `${Number(selectedProvider.telemetry.memory.used).toFixed(1)} / ${selectedProvider.telemetry?.memory?.limit ?? "--"} GB`}
                </span>
              </div>
              <div>
                <strong>Disk</strong>
                <span>
                  {selectedProvider.telemetry?.disk?.used == null
                    ? "--"
                    : `${Number(selectedProvider.telemetry.disk.used).toFixed(1)} / ${selectedProvider.telemetry?.disk?.limit ?? "--"} GB`}
                </span>
              </div>
              <div>
                <strong>Running metric</strong>
                <span>
                  {selectedProvider.telemetry?.running?.used == null
                    ? "--"
                    : `${selectedProvider.telemetry.running.used} / ${selectedProvider.telemetry?.running?.limit ?? "--"} ${selectedProvider.telemetry?.running?.unit || ""}`}
                </span>
              </div>
              <div>
                <strong>Reason</strong>
                <span>
                  {selectedProvider.unavailableReason ||
                    selectedProvider.error ||
                    "healthy"}
                </span>
              </div>
            </div>
          </div>
          <div className="resource-session-shell depth-recessed">
            <div className="section-row">
              <div>
                <h2>Leases ({selectedLeaseGroups.length})</h2>
              </div>
            </div>
            <div className="provider-lease-grid">
              {selectedLeaseGroups.map((group: any) => (
                <ProviderLeaseCard
                  key={leaseGroupKey(group)}
                  group={group}
                  selected={
                    selectedLeaseGroup != null &&
                    leaseGroupKey(group) === leaseGroupKey(selectedLeaseGroup)
                  }
                  onSelect={() => setSelectedLeaseId(leaseGroupKey(group))}
                />
              ))}
              {selectedLeaseGroups.length === 0 ? (
                <div className="dashboard-empty">
                  No lease groups reported for this provider.
                </div>
              ) : null}
            </div>
            {selectedLeaseGroup ? (
              <MonitorLeaseDetailPanel group={selectedLeaseGroup} />
            ) : null}
            <div className="section-row">
              <div>
                <h2>
                  Sessions (
                  {sessionScope === "provider"
                    ? selectedSessions.length
                    : scopedSessions.length}
                  )
                </h2>
                <p className="count">
                  {sessionScope === "provider"
                    ? "full provider truth surface"
                    : "scoped to selected lease"}
                </p>
              </div>
              <div
                className="segmented-toggle"
                data-testid="session-scope-toggle"
              >
                <button
                  type="button"
                  className={`ghost-btn${sessionScope === "lease" ? " is-active" : ""}`}
                  onClick={() => setSessionScope("lease")}
                  disabled={!selectedLeaseGroup}
                >
                  Selected lease
                </button>
                <button
                  type="button"
                  className={`ghost-btn${sessionScope === "provider" ? " is-active" : ""}`}
                  onClick={() => setSessionScope("provider")}
                >
                  All provider sessions
                </button>
              </div>
            </div>
            <table className="resource-table-dense">
              <thead>
                <tr>
                  <th>Session</th>
                  <th>Thread</th>
                  <th>Lease</th>
                  <th>Member</th>
                  <th>Status</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {scopedSessions.map((session: any) => (
                  <tr key={session.id}>
                    <td className="mono">{shortId(session.id, 12)}</td>
                    <td>
                      {session.threadId ? (
                        <Link to={`/thread/${session.threadId}`}>
                          {shortId(session.threadId, 12)}
                        </Link>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>
                      {session.leaseId ? (
                        <Link to={`/lease/${session.leaseId}`}>
                          {shortId(session.leaseId, 12)}
                        </Link>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>{session.memberName || session.memberId || "-"}</td>
                    <td>{session.status}</td>
                    <td>
                      {session.startedAt
                        ? new Date(session.startedAt).toLocaleString()
                        : "-"}
                    </td>
                  </tr>
                ))}
                {scopedSessions.length === 0 ? (
                  <tr>
                    <td colSpan={6}>
                      {sessionScope === "provider"
                        ? "No sessions reported for this provider."
                        : "No sessions reported for the selected lease group."}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          </>
          ) : (
            <div className="dashboard-empty">Select a provider from the list.</div>
          )}
        </div>
      </section>

      <section className="resource-section-shell depth-secondary" id="lease-health">
        <div className="section-row">
          <div>
            <h2>Lease Health</h2>
          </div>
          <Link className="quick-link" to="/leases">
            Legacy flat table
          </Link>
        </div>
        <div className="resource-overview-strip">
          <span className="resource-overview-pill">
            <span className="resource-overview-label">active drift</span>
            <strong>{activeDriftLeases.length}</strong>
          </span>
          <span className="resource-overview-pill">
            <span className="resource-overview-label">detached residue</span>
            <strong>{detachedResidueLeases.length}</strong>
          </span>
          <span className="resource-overview-pill">
            <span className="resource-overview-label">orphan cleanup</span>
            <strong>{orphanCleanupLeases.length}</strong>
          </span>
          <span className="resource-overview-pill">
            <span className="resource-overview-label">healthy</span>
            <strong>{healthyCapacityLeases.length}</strong>
          </span>
        </div>
        {hasPrimaryLeaseAttention ? (
          <div className="lease-cluster-grid">
            {activeDriftLeases.length > 0 ? (
              <article className="depth-primary">
                <h2>Active Drift ({activeDriftLeases.length})</h2>
                <table>
                  <thead>
                    <tr>
                      <th>Lease</th>
                      <th>Provider</th>
                      <th>Thread</th>
                      <th>State</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeDriftLeases.slice(0, 8).map((item: any) => (
                      <tr key={item.lease_id}>
                        <td>
                          <Link to={item.lease_url}>
                            {shortId(item.lease_id, 12)}
                          </Link>
                        </td>
                        <td>{item.provider}</td>
                        <td>
                          {item.thread?.thread_id ? (
                            <Link to={item.thread.thread_url}>
                              {shortId(item.thread.thread_id, 12)}
                            </Link>
                          ) : (
                            <span className="orphan">orphan</span>
                          )}
                        </td>
                        <td>
                          <StateBadge badge={item.state_badge} />
                        </td>
                        <td>{item.updated_ago}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>
            ) : null}

            {detachedResidueLeases.length > 0 ? (
              <article className="depth-primary">
                <h2>Detached Residue ({detachedResidueLeases.length})</h2>
                <table>
                  <thead>
                    <tr>
                      <th>Lease</th>
                      <th>Provider</th>
                      <th>Thread</th>
                      <th>State</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detachedResidueLeases.slice(0, 8).map((item: any) => (
                      <tr key={item.lease_id}>
                        <td>
                          <Link to={item.lease_url}>
                            {shortId(item.lease_id, 12)}
                          </Link>
                        </td>
                        <td>{item.provider}</td>
                        <td>
                          {item.thread?.thread_id ? (
                            <Link to={item.thread.thread_url}>
                              {shortId(item.thread.thread_id, 12)}
                            </Link>
                          ) : (
                            <span className="orphan">orphan</span>
                          )}
                        </td>
                        <td>
                          <StateBadge badge={item.state_badge} />
                        </td>
                        <td>{item.updated_ago}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>
            ) : null}
          </div>
        ) : null}

        {hasSecondaryLeaseAttention ? (
          <div className="lease-cluster-grid">
            <article className="depth-recessed">
              <h2>Cleanup Backlog ({orphanCleanupLeases.length})</h2>
              <table>
                <thead>
                  <tr>
                    <th>Lease</th>
                    <th>Provider</th>
                    <th>Instance</th>
                    <th>State</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {orphanCleanupLeases.slice(0, 8).map((item: any) => (
                    <tr key={item.lease_id}>
                      <td>
                        <Link to={item.lease_url}>
                          {shortId(item.lease_id, 12)}
                        </Link>
                      </td>
                      <td>{item.provider}</td>
                      <td className="mono">{shortId(item.instance_id, 12)}</td>
                      <td>
                        <StateBadge badge={item.state_badge} />
                      </td>
                      <td>{item.updated_ago}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </article>
          </div>
        ) : null}

        {healthyCapacityLeases.length > 0 ? (
          <details className="lease-details-shell depth-recessed">
            <summary>Healthy Capacity ({healthyCapacityLeases.length})</summary>
            <table>
              <thead>
                <tr>
                  <th>Lease</th>
                  <th>Provider</th>
                  <th>Thread</th>
                  <th>State</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {healthyCapacityLeases.slice(0, 8).map((item: any) => (
                  <tr key={item.lease_id}>
                    <td>
                      <Link to={item.lease_url}>
                        {shortId(item.lease_id, 12)}
                      </Link>
                    </td>
                    <td>{item.provider}</td>
                    <td>
                      {item.thread?.thread_id ? (
                        <Link to={item.thread.thread_url}>
                          {shortId(item.thread.thread_id, 12)}
                        </Link>
                      ) : (
                        <span className="orphan">orphan</span>
                      )}
                    </td>
                    <td>
                      <StateBadge badge={item.state_badge} />
                    </td>
                    <td>{item.updated_ago}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        ) : null}

        {!hasPrimaryLeaseAttention &&
        !hasSecondaryLeaseAttention &&
        healthyCapacityLeases.length === 0 ? (
          <div className="dashboard-empty">No lease groups reported yet.</div>
        ) : null}

        <details className="lease-details-shell depth-recessed">
          <summary>All leases ({leases.length})</summary>
          <table>
            <thead>
              <tr>
                <th>Lease ID</th>
                <th>Provider</th>
                <th>Instance ID</th>
                <th>Thread</th>
                <th>State</th>
                <th>Updated</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {leases.map((item: any) => (
                <tr key={item.lease_id}>
                  <td>
                    <Link to={item.lease_url}>{item.lease_id}</Link>
                  </td>
                  <td>{item.provider}</td>
                  <td className="mono">
                    {item.instance_id?.slice(0, 12) || "-"}
                  </td>
                  <td>
                    {item.thread.thread_id ? (
                      <Link to={item.thread.thread_url}>
                        {item.thread.thread_id.slice(0, 8)}
                      </Link>
                    ) : (
                      <span className="orphan">orphan</span>
                    )}
                  </td>
                  <td>
                    <StateBadge badge={item.state_badge} />
                  </td>
                  <td>{item.updated_ago}</td>
                  <td className="error">{item.error || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>
    </div>
  );
}

// Page: Threads List
function ThreadsPage() {
  const [data, setData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState<boolean>(false);
  const [offset, setOffset] = React.useState<number>(0);
  const [limit, setLimit] = React.useState<number>(50);

  const loadThreads = React.useCallback(async () => {
    setLoading(true);
    try {
      const payload = await fetchAPI(
        `/threads?offset=${offset}&limit=${limit}`,
      );
      setData(payload);
    } finally {
      setLoading(false);
    }
  }, [offset, limit]);

  React.useEffect(() => {
    void loadThreads();
  }, [loadThreads]);

  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }
  const pagination = data.pagination || {};
  const total = Number(pagination.total || data.count || 0);
  const currentCount = Number(data.count || 0);
  const from = total > 0 ? offset + 1 : 0;
  const to = offset + currentCount;
  const page = Number(pagination.page || 1);

  return (
    <div className="page" data-testid="page-threads">
      <p className="description">
        Global thread index. Start here to find the active run, then drill into
        session, lease, and trace detail.
      </p>
      <p className="count">
        Showing {from}-{to} of {total} | page {page}
      </p>
      <section>
        <div className="pagination-bar">
          <div className="pagination-controls">
            <button
              className="ghost-btn"
              onClick={() => setOffset(Number(pagination.prev_offset))}
              disabled={loading || !pagination.has_prev}
            >
              Prev
            </button>
            <button
              className="ghost-btn"
              onClick={() => setOffset(Number(pagination.next_offset))}
              disabled={loading || !pagination.has_next}
            >
              Next
            </button>
            <button
              className="ghost-btn"
              onClick={() => void loadThreads()}
              disabled={loading}
            >
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          <div className="pagination-size">
            <span>Rows:</span>
            <select
              value={limit}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setOffset(0);
              }}
              disabled={loading}
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Thread ID</th>
              <th>Mode</th>
              <th>Sessions</th>
              <th>Last Active</th>
              <th>Lease</th>
              <th>Provider</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((item: any) => (
              <tr key={item.thread_id}>
                <td>
                  <Link to={item.thread_url}>{item.thread_id.slice(0, 8)}</Link>
                </td>
                <td>
                  {item.thread_mode || "normal"} / trace=
                  {item.keep_full_trace ? "full" : "latest"}
                </td>
                <td>{item.session_count}</td>
                <td>{item.last_active_ago}</td>
                <td>
                  {item.lease.lease_id ? (
                    <Link to={item.lease.lease_url}>{item.lease.lease_id}</Link>
                  ) : (
                    "-"
                  )}
                </td>
                <td>{item.lease.provider || "-"}</td>
                <td>
                  <StateBadge badge={item.state_badge} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function TracesPage() {
  const [data, setData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState<boolean>(false);
  const [offset, setOffset] = React.useState<number>(0);
  const [limit, setLimit] = React.useState<number>(50);

  const loadTraces = React.useCallback(async () => {
    setLoading(true);
    try {
      const payload = await fetchAPI(`/traces?offset=${offset}&limit=${limit}`);
      setData(payload);
    } finally {
      setLoading(false);
    }
  }, [offset, limit]);

  React.useEffect(() => {
    void loadTraces();
  }, [loadTraces]);

  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }
  const pagination = data.pagination || {};
  const total = Number(pagination.total || data.count || 0);
  const currentCount = Number(data.count || 0);
  const from = total > 0 ? offset + 1 : 0;
  const to = offset + currentCount;
  const page = Number(pagination.page || 1);

  return (
    <div className="page" data-testid="page-traces">
      <p className="description">
        Run-level trace index for debugging tool calls, checkpoints, and runtime
        transitions across monitored threads.
      </p>
      <p className="count">
        Showing {from}-{to} of {total} | page {page}
      </p>
      <section>
        <div className="pagination-bar">
          <div className="pagination-controls">
            <button
              className="ghost-btn"
              onClick={() => setOffset(Number(pagination.prev_offset))}
              disabled={loading || !pagination.has_prev}
            >
              Prev
            </button>
            <button
              className="ghost-btn"
              onClick={() => setOffset(Number(pagination.next_offset))}
              disabled={loading || !pagination.has_next}
            >
              Next
            </button>
            <button
              className="ghost-btn"
              onClick={() => void loadTraces()}
              disabled={loading}
            >
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          <div className="pagination-size">
            <span>Rows:</span>
            <select
              value={limit}
              onChange={(e) => {
                setLimit(Number(e.target.value));
                setOffset(0);
              }}
              disabled={loading}
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Thread</th>
              <th>Run</th>
              <th>Mode</th>
              <th>Events</th>
              <th>Tool Calls</th>
              <th>Started</th>
              <th>Last Event</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((item: any) => (
              <tr key={`${item.thread_id}-${item.run_id}`}>
                <td>
                  <Link to={item.thread_url}>
                    {item.thread_id.slice(0, 18)}
                  </Link>
                </td>
                <td className="mono">{shortId(item.run_id, 12)}</td>
                <td>
                  {item.thread_mode || "normal"} / trace=
                  {item.keep_full_trace ? "full" : "latest"}
                </td>
                <td>{item.event_count}</td>
                <td>
                  {item.tool_call_count} / {item.tool_result_count}
                </td>
                <td>{item.started_ago || "-"}</td>
                <td>{item.last_event_ago || "-"}</td>
                <td>{item.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

// Page: Thread Detail
function ThreadDetailPage() {
  const { threadId } = useParams();
  const location = useLocation();
  const [data, setData] = React.useState<any>(null);
  const initialRunId = React.useMemo(
    () => new URLSearchParams(location.search).get("run") || "",
    [location.search],
  );

  React.useEffect(() => {
    fetchAPI(`/thread/${threadId}`).then(setData);
  }, [threadId]);

  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }
  const threadIsActive = Array.isArray(data?.sessions?.items)
    ? data.sessions.items.some((s: any) => s.status === "active")
    : false;

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Thread: {data.thread_id.slice(0, 8)}</h1>
      <p className="count">
        mode: {data.thread_mode || "normal"} | trace:{" "}
        {data.keep_full_trace ? "full" : "latest"}
      </p>

      <section>
        <h2>
          {data.sessions.title} ({data.sessions.count})
        </h2>
        <table>
          <thead>
            <tr>
              <th>Session ID</th>
              <th>Status</th>
              <th>Started</th>
              <th>Ended</th>
              <th>Lease</th>
              <th>State</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {data.sessions.items.map((s: any) => (
              <tr key={s.session_id}>
                <td>
                  <Link to={s.session_url}>{s.session_id.slice(0, 8)}</Link>
                </td>
                <td>{s.status}</td>
                <td>{s.started_ago}</td>
                <td>{s.ended_ago || "-"}</td>
                <td>
                  {s.lease.lease_id ? (
                    <Link to={s.lease.lease_url}>{s.lease.lease_id}</Link>
                  ) : (
                    "-"
                  )}
                </td>
                <td>
                  <StateBadge badge={s.state_badge} />
                </td>
                <td className="error">{s.error || "-"}</td>
              </tr>
            ))}
            {data.sessions.items.length === 0 && (
              <tr>
                <td colSpan={7}>No sessions recorded for this thread.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section>
        <h2>{data.related_leases.title}</h2>
        <ul>
          {data.related_leases.items.map((l: any) => (
            <li key={l.lease_id}>
              <Link to={l.lease_url}>{l.lease_id}</Link>
            </li>
          ))}
          {data.related_leases.items.length === 0 && (
            <li className="empty-list">No related leases for this thread.</li>
          )}
        </ul>
      </section>

      <section className="trace-section-shell">
        <h2>Live Trace</h2>
        <p className="description">
          Conversation, event stream, and grouped steps for the selected run.
          Use this after locating the right session or lease above.
        </p>
        <ThreadTraceSection
          threadId={data.thread_id}
          autoRefreshEnabled={threadIsActive}
          initialRunId={initialRunId}
        />
      </section>
    </div>
  );
}

function summarizeTraceEvent(eventType: string, payload: any): string {
  if (eventType === "tool_call")
    return `${payload?.name || "tool"}(${JSON.stringify(payload?.args || {})})`;
  if (eventType === "tool_result")
    return `${payload?.name || "tool"} -> ${String(payload?.content || "").slice(0, 240)}`;
  if (eventType === "text") return String(payload?.content || "").slice(0, 120);
  if (eventType === "status") {
    const state =
      typeof payload?.state === "string"
        ? payload.state
        : JSON.stringify(payload?.state || "-");
    return `state=${state} calls=${payload?.call_count ?? "-"}`;
  }
  if (eventType === "error") return payload?.error || "error";
  if (eventType === "done") return "done";
  return JSON.stringify(payload).slice(0, 120);
}

type TraceItem = {
  seq: number | null;
  run_id: string | null;
  created_at?: string | null;
  created_ago?: string | null;
  event_type: string;
  actor: "assistant" | "tool" | "runtime";
  summary: string;
  payload: any;
};

function normalizeTraceEvent(
  eventType: string,
  payload: any,
): TraceItem | null {
  const seq = payload?._seq ?? null;
  const run_id = payload?._run_id ?? null;

  if (eventType === "text") {
    const content =
      typeof payload?.content === "string"
        ? payload.content
        : String(payload?.content ?? "");
    if (!content) return null;
    return {
      seq,
      run_id,
      event_type: "assistant_text",
      actor: "assistant",
      summary: content,
      payload,
    };
  }

  if (eventType === "tool_call") {
    return {
      seq,
      run_id,
      event_type: "tool_call",
      actor: "tool",
      summary: `${payload?.name || "tool"}`,
      payload,
    };
  }

  if (eventType === "tool_result") {
    return {
      seq,
      run_id,
      event_type: "tool_result",
      actor: "tool",
      summary: `${payload?.name || "tool"}`,
      payload,
    };
  }

  if (eventType === "status") {
    const state =
      typeof payload?.state === "string"
        ? payload.state
        : JSON.stringify(payload?.state || "-");
    return {
      seq,
      run_id,
      event_type: "status",
      actor: "runtime",
      summary: `state=${state} calls=${payload?.call_count ?? "-"}`,
      payload,
    };
  }

  if (
    eventType === "error" ||
    eventType === "cancelled" ||
    eventType === "done"
  ) {
    return {
      seq,
      run_id,
      event_type: eventType,
      actor: "runtime",
      summary: summarizeTraceEvent(eventType, payload),
      payload,
    };
  }
  return null;
}

function normalizeStoredTraceEvent(
  row: any,
  fallbackRunId: string | null,
): TraceItem | null {
  const payload = row?.payload || {};
  if (payload?._seq == null && row?.seq != null) payload._seq = row.seq;
  if (payload?._run_id == null && fallbackRunId)
    payload._run_id = fallbackRunId;
  const normalized = normalizeTraceEvent(
    String(row?.event_type || ""),
    payload,
  );
  if (!normalized) return null;
  return {
    ...normalized,
    seq: row?.seq ?? normalized.seq,
    run_id: fallbackRunId || normalized.run_id,
    created_at: row?.created_at || null,
    created_ago: row?.created_ago || null,
  };
}

function mergeTraceItems(prev: TraceItem[], next: TraceItem): TraceItem[] {
  const last = prev.length ? prev[prev.length - 1] : null;

  // @@@streaming-text-fold - collapse token-level text stream into one assistant step for readable trace timeline.
  if (
    next.event_type === "assistant_text" &&
    last &&
    last.event_type === "assistant_text" &&
    last.run_id === next.run_id
  ) {
    const merged = [...prev];
    merged[merged.length - 1] = {
      ...last,
      seq: next.seq ?? last.seq,
      summary: `${last.summary}${next.summary}`,
      payload: next.payload,
    };
    return merged;
  }

  // @@@status-coalesce - keep only latest status snapshot for same run to reduce noise.
  if (
    next.event_type === "status" &&
    last &&
    last.event_type === "status" &&
    last.run_id === next.run_id
  ) {
    const merged = [...prev];
    merged[merged.length - 1] = next;
    return merged;
  }

  return [...prev, next];
}

type TraceStep = {
  step: number;
  run_id: string | null;
  seq_start: number | null;
  seq_end: number | null;
  created_ago: string | null;
  assistant_text: string;
  tool_name: string | null;
  tool_args: any;
  command_line: string | null;
  tool_output: string | null;
  runtime_notes: string[];
  raw_items: TraceItem[];
};

function buildTraceSteps(items: TraceItem[]): TraceStep[] {
  const steps: TraceStep[] = [];
  let assistantBuffer: string[] = [];
  let pending: Omit<TraceStep, "step"> | null = null;

  const pushStep = (step: Omit<TraceStep, "step">) => {
    steps.push({ ...step, step: steps.length + 1 });
  };

  for (const item of items) {
    if (item.event_type === "assistant_text") {
      if (pending) {
        pending.runtime_notes.push(item.summary);
        pending.raw_items.push(item);
        pending.seq_end = item.seq ?? pending.seq_end;
      } else {
        assistantBuffer.push(item.summary);
      }
      continue;
    }

    if (item.event_type === "tool_call") {
      if (pending) {
        pushStep(pending);
        pending = null;
      }
      pending = {
        run_id: item.run_id,
        seq_start: item.seq,
        seq_end: item.seq,
        created_ago: item.created_ago || null,
        assistant_text: assistantBuffer.join("\n").trim(),
        tool_name: item.payload?.name || item.summary,
        tool_args: item.payload?.args || {},
        command_line: item.payload?.args?.CommandLine
          ? String(item.payload.args.CommandLine)
          : null,
        tool_output: null,
        runtime_notes: [],
        raw_items: [item],
      };
      assistantBuffer = [];
      continue;
    }

    if (item.event_type === "tool_result") {
      if (pending && !pending.tool_output) {
        pending.tool_output = String(item.payload?.content || "(no output)");
        pending.raw_items.push(item);
        pending.seq_end = item.seq ?? pending.seq_end;
      } else {
        pushStep({
          run_id: item.run_id,
          seq_start: item.seq,
          seq_end: item.seq,
          created_ago: item.created_ago || null,
          assistant_text: assistantBuffer.join("\n").trim(),
          tool_name: item.payload?.name || item.summary,
          tool_args: null,
          command_line: null,
          tool_output: String(item.payload?.content || "(no output)"),
          runtime_notes: [],
          raw_items: [item],
        });
        assistantBuffer = [];
      }
      continue;
    }

    const runtimeNote =
      item.event_type === "status"
        ? formatStatusSummary(item.payload)
        : item.summary;
    if (pending) {
      pending.runtime_notes.push(runtimeNote);
      pending.raw_items.push(item);
      pending.seq_end = item.seq ?? pending.seq_end;
      if (
        item.event_type === "error" ||
        item.event_type === "cancelled" ||
        item.event_type === "done"
      ) {
        pushStep(pending);
        pending = null;
      }
    } else {
      pushStep({
        run_id: item.run_id,
        seq_start: item.seq,
        seq_end: item.seq,
        created_ago: item.created_ago || null,
        assistant_text: assistantBuffer.join("\n").trim(),
        tool_name: null,
        tool_args: null,
        command_line: null,
        tool_output: null,
        runtime_notes: [runtimeNote],
        raw_items: [item],
      });
      assistantBuffer = [];
    }
  }

  if (pending) pushStep(pending);

  const remain = assistantBuffer.join("\n").trim();
  if (remain) {
    pushStep({
      run_id: items.length ? items[items.length - 1].run_id : null,
      seq_start: null,
      seq_end: null,
      created_ago: null,
      assistant_text: remain,
      tool_name: null,
      tool_args: null,
      command_line: null,
      tool_output: null,
      runtime_notes: [],
      raw_items: [],
    });
  }

  return steps;
}

function shortId(value: string | null, size = 8): string {
  if (!value) return "-";
  return String(value).slice(0, size);
}

function evalThreadLabel(
  threadId: string | null,
  evaluationId: string | null,
): string {
  if (!threadId) return "-";
  if (!evaluationId) return shortId(threadId, 20);
  const prefix = `swebench-${evaluationId}-`;
  if (threadId.startsWith(prefix)) {
    const instanceId = threadId.slice(prefix.length);
    return instanceId || shortId(threadId, 20);
  }
  return shortId(threadId, 20);
}

function formatPct(value: any): string {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return `${num.toFixed(1)}%`;
}

function formatResolvedScore(item: any): string {
  const resolved = Number(item?.score?.resolved_instances ?? 0);
  const total = Number(item?.score?.total_instances ?? 0);
  return `${resolved}/${total} (${formatPct(item?.score?.resolved_rate_pct)})`;
}

function evalProgress(item: any): {
  done: number;
  target: number;
  running: number;
  pct: number;
  mode: "thread_rows" | "session_rows" | "checkpoint_estimate";
} {
  const doneRaw = Number(item?.threads_done ?? 0);
  const runningRaw = Number(item?.threads_running ?? 0);
  const targetRaw = Number(item?.slice_count ?? item?.threads_total ?? 0);
  const modeRaw = String(item?.progress_source || "");
  const done = Number.isFinite(doneRaw) ? Math.max(0, doneRaw) : 0;
  const running = Number.isFinite(runningRaw) ? Math.max(0, runningRaw) : 0;
  const targetCandidate = Number.isFinite(targetRaw)
    ? Math.max(0, targetRaw)
    : 0;
  const mode =
    modeRaw === "checkpoint_estimate" || modeRaw === "session_rows"
      ? modeRaw
      : "thread_rows";
  const target =
    targetCandidate > 0 ? targetCandidate : Math.max(done + running, 0);
  // @@@progress-active-ratio - evaluation threads can be running long before any thread reaches "done".
  // Use (done + running) to reflect visible in-flight progress instead of a flat 0% bar.
  const active = Math.min(target, done + running);
  const pct = target > 0 ? Math.min(100, (active / target) * 100) : 0;
  return { done, target, running, pct, mode };
}

function formatProgressSummary(progress: {
  done: number;
  target: number;
  running: number;
  pct: number;
  mode: "thread_rows" | "session_rows" | "checkpoint_estimate";
}): string {
  const pending = Math.max(
    0,
    progress.target - progress.done - progress.running,
  );
  const activeLabel =
    progress.mode === "checkpoint_estimate" ? "Started" : "In Progress";
  const sourceSuffix =
    progress.mode === "thread_rows" ? "" : ` · source=${progress.mode}`;
  return `Total ${progress.target} · Completed ${progress.done} · ${activeLabel} ${progress.running} · Pending ${pending} · Progress ${formatPct(progress.pct)}${sourceSuffix}`;
}

function formatStatusSummary(payload: any): string {
  const stateText =
    typeof payload?.state === "string"
      ? payload.state
      : payload?.state?.state || JSON.stringify(payload?.state || "-");
  const calls = payload?.call_count ?? "-";
  const inTokens = payload?.input_tokens ?? payload?.token_count ?? "-";
  const outTokens = payload?.output_tokens ?? "-";
  return `state=${stateText} calls=${calls} tokens=${inTokens}/${outTokens}`;
}

function conversationText(content: any): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && part.type === "text")
          return String(part.text || "");
        return JSON.stringify(part);
      })
      .join("");
  }
  if (content == null) return "";
  return typeof content === "object"
    ? JSON.stringify(content, null, 2)
    : String(content);
}

function ConversationTraceCard({
  message,
  index,
}: {
  message: any;
  index: number;
}) {
  const msgType = String(message?.type || "Unknown");
  const msgTypeKey = msgType.toLowerCase();
  const text = conversationText(message?.content);
  const toolCalls = Array.isArray(message?.tool_calls)
    ? message.tool_calls
    : [];
  return (
    <article className="conversation-card" data-msg-type={msgTypeKey}>
      <header className="trace-card-header">
        <div className="trace-card-meta">
          <span className="trace-step">[{index}]</span>
          <span className="trace-event">{msgType}</span>
        </div>
        <span className="mono trace-run-id">
          id {shortId(message?.id || "-", 12)}
        </span>
      </header>

      {toolCalls.length > 0 && (
        <div className="trace-block-wrap">
          <div className="trace-label">tool_calls</div>
          <pre className="trace-block">
            {JSON.stringify(toolCalls, null, 2)}
          </pre>
        </div>
      )}

      {message?.tool_call_id && (
        <div className="trace-block-wrap">
          <div className="trace-label">tool_call_id</div>
          <pre className="trace-block">{String(message.tool_call_id)}</pre>
        </div>
      )}

      <div className="trace-block-wrap">
        <div className="trace-label">content</div>
        <pre className="trace-block trace-assistant-text">
          {text || "(empty)"}
        </pre>
      </div>

      <details className="trace-details">
        <summary>Raw message</summary>
        <pre className="json-payload trace-payload">
          {JSON.stringify(message, null, 2)}
        </pre>
      </details>
    </article>
  );
}

function TraceCard({ item }: { item: TraceItem }) {
  const statusText =
    item.event_type === "status" ? formatStatusSummary(item.payload) : null;
  const commandLine = item.payload?.args?.CommandLine;
  const toolArgs = item.payload?.args;
  const toolOutput = item.payload?.content;
  return (
    <article className={`trace-card trace-card-${item.actor}`}>
      <header className="trace-card-header">
        <div className="trace-card-meta">
          <span className="trace-step">#{item.seq ?? "-"}</span>
          <span className={`trace-actor trace-${item.actor}`}>
            {item.actor}
          </span>
          <span className="trace-event">{item.event_type}</span>
        </div>
        <span className="mono trace-run-id">run {shortId(item.run_id)}</span>
      </header>

      {item.event_type === "assistant_text" && (
        <pre className="trace-block trace-assistant-text">{item.summary}</pre>
      )}

      {item.event_type === "tool_call" && (
        <div className="trace-block-wrap">
          <div className="trace-label">Tool</div>
          <pre className="trace-block">
            {item.payload?.name || item.summary}
          </pre>
          {commandLine && (
            <>
              <div className="trace-label">CommandLine</div>
              <pre className="trace-block trace-command">
                {String(commandLine)}
              </pre>
            </>
          )}
          <div className="trace-label">Args</div>
          <pre className="trace-block">
            {JSON.stringify(toolArgs || {}, null, 2)}
          </pre>
        </div>
      )}

      {item.event_type === "tool_result" && (
        <div className="trace-block-wrap">
          <div className="trace-label">Tool</div>
          <pre className="trace-block">
            {item.payload?.name || item.summary}
          </pre>
          <div className="trace-label">Output</div>
          <pre className="trace-block trace-output">
            {String(toolOutput || "(no output)")}
          </pre>
        </div>
      )}

      {item.event_type === "status" && (
        <div className="trace-block-wrap">
          <div className="trace-label">Runtime</div>
          <pre className="trace-block">{statusText}</pre>
        </div>
      )}

      {(item.event_type === "error" ||
        item.event_type === "cancelled" ||
        item.event_type === "done") && (
        <pre className="trace-block">{item.summary}</pre>
      )}

      <details className="trace-details">
        <summary>Raw payload</summary>
        <pre className="json-payload trace-payload">
          {JSON.stringify(item.payload, null, 2)}
        </pre>
      </details>
    </article>
  );
}

function TraceStepCard({ step }: { step: TraceStep }) {
  return (
    <article className="trace-step-card">
      <header className="trace-step-header">
        <div className="trace-step-meta">
          <span className="trace-step-index">Step {step.step}</span>
          <span className="mono">
            seq {step.seq_start ?? "-"}..{step.seq_end ?? "-"}
          </span>
          <span className="mono">run {shortId(step.run_id)}</span>
        </div>
        <span className="count">{step.created_ago || "-"}</span>
      </header>

      {step.assistant_text && (
        <div className="trace-step-block">
          <div className="trace-label">Intent</div>
          <pre className="trace-block trace-assistant-text">
            {step.assistant_text}
          </pre>
        </div>
      )}

      {step.tool_name && (
        <div className="trace-step-block">
          <div className="trace-label">Action</div>
          <pre className="trace-block">{step.tool_name}</pre>
          {step.command_line && (
            <>
              <div className="trace-label">CommandLine</div>
              <pre className="trace-block trace-command">
                {step.command_line}
              </pre>
            </>
          )}
          {step.tool_args && (
            <>
              <div className="trace-label">Args</div>
              <pre className="trace-block">
                {JSON.stringify(step.tool_args, null, 2)}
              </pre>
            </>
          )}
        </div>
      )}

      {step.tool_output != null && (
        <div className="trace-step-block">
          <div className="trace-label">Observation</div>
          <pre className="trace-block trace-output">{step.tool_output}</pre>
        </div>
      )}

      {step.runtime_notes.length > 0 && (
        <div className="trace-step-block">
          <div className="trace-label">Runtime</div>
          <pre className="trace-block">{step.runtime_notes.join("\n")}</pre>
        </div>
      )}

      <details className="trace-details">
        <summary>Raw events ({step.raw_items.length})</summary>
        {step.raw_items.map((item, idx) => (
          <div key={`${item.seq || "na"}-${idx}`} className="trace-raw-item">
            <div className="trace-raw-item-title">
              <span className="mono">#{item.seq || "-"}</span>
              <span>{item.event_type}</span>
            </div>
            <pre className="json-payload trace-payload">
              {JSON.stringify(item.payload, null, 2)}
            </pre>
          </div>
        ))}
      </details>
    </article>
  );
}

function ThreadTraceSection({
  threadId,
  autoRefreshEnabled,
  initialRunId = "",
}: {
  threadId: string;
  autoRefreshEnabled: boolean;
  initialRunId?: string;
}) {
  const [traceEvents, setTraceEvents] = React.useState<TraceItem[]>([]);
  const [traceError, setTraceError] = React.useState<string | null>(null);
  const [traceLoading, setTraceLoading] = React.useState<boolean>(false);
  const [rawEventCount, setRawEventCount] = React.useState<number>(0);
  const [streamState, setStreamState] = React.useState<
    "idle" | "polling" | "error"
  >("idle");
  const [eventFilter, setEventFilter] = React.useState<
    "all" | "assistant" | "tool" | "runtime"
  >("all");
  const [traceView, setTraceView] = React.useState<
    "conversation" | "events" | "steps"
  >("conversation");
  const [showRawTable, setShowRawTable] = React.useState<boolean>(false);
  const [selectedRunId, setSelectedRunId] = React.useState<string>("");
  const [runCandidates, setRunCandidates] = React.useState<any[]>([]);
  const [autoRefresh, setAutoRefresh] = React.useState<boolean>(true);
  const [conversationMessages, setConversationMessages] = React.useState<any[]>(
    [],
  );
  const [conversationLoading, setConversationLoading] =
    React.useState<boolean>(false);
  const [conversationError, setConversationError] = React.useState<
    string | null
  >(null);

  const loadTrace = React.useCallback(
    (runId: string) => {
      if (!threadId) return;
      const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
      setTraceLoading(true);
      setTraceError(null);
      setStreamState("polling");
      fetchAPI(`/thread/${threadId}/trace${query}`)
        .then((payload) => {
          setRawEventCount(payload?.event_count || 0);
          setRunCandidates(payload?.run_candidates || []);
          if (!runId && payload?.run_id) {
            setSelectedRunId((prev) => prev || String(payload.run_id));
          }
          const normalized = (payload?.events || [])
            .map((row: any) =>
              normalizeStoredTraceEvent(row, payload?.run_id || runId || null),
            )
            .filter(Boolean) as TraceItem[];
          const merged = normalized.reduce(
            (acc: TraceItem[], item) => mergeTraceItems(acc, item),
            [],
          );
          setTraceEvents(merged);
          setStreamState("idle");
        })
        .catch((e) => {
          setTraceError(e.message);
          setStreamState("error");
        })
        .finally(() => setTraceLoading(false));
    },
    [threadId],
  );

  const loadConversation = React.useCallback(() => {
    if (!threadId) return;
    setConversationLoading(true);
    setConversationError(null);
    fetchAPI(`/thread/${threadId}/conversation`)
      .then((payload) => {
        setConversationMessages(
          Array.isArray(payload?.messages) ? payload.messages : [],
        );
      })
      .catch((e) => setConversationError(e.message))
      .finally(() => setConversationLoading(false));
  }, [threadId]);

  React.useEffect(() => {
    if (!threadId) return;
    setTraceEvents([]);
    setRunCandidates([]);
    setSelectedRunId(initialRunId);
    loadTrace(initialRunId);
    loadConversation();
  }, [threadId, initialRunId, loadTrace, loadConversation]);

  React.useEffect(() => {
    if (!selectedRunId) return;
    loadTrace(selectedRunId);
  }, [selectedRunId, loadTrace]);

  React.useEffect(() => {
    if (!threadId || !autoRefreshEnabled || !autoRefresh) return;
    const timer = window.setInterval(() => {
      loadTrace(selectedRunId);
      loadConversation();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [
    threadId,
    autoRefreshEnabled,
    autoRefresh,
    selectedRunId,
    loadTrace,
    loadConversation,
  ]);

  const traceTail = traceEvents.slice(-300);
  const visibleTrace = traceTail.filter(
    (item) => eventFilter === "all" || item.actor === eventFilter,
  );
  const traceSteps = buildTraceSteps(visibleTrace);
  const conversationTail = conversationMessages.slice(-200);
  const traceStats = {
    assistant: traceTail.filter((item) => item.actor === "assistant").length,
    tool: traceTail.filter((item) => item.actor === "tool").length,
    runtime: traceTail.filter((item) => item.actor === "runtime").length,
  };

  return (
    <section>
      <h2>
        Thread Trace{" "}
        {traceView === "conversation"
          ? "Conversation"
          : traceView === "events"
            ? "Events"
            : "Steps"}{" "}
        (
        {traceView === "conversation"
          ? `${conversationTail.length} messages`
          : traceView === "events"
            ? `${visibleTrace.length} events`
            : `${traceSteps.length} steps / ${visibleTrace.length} events`}
        )
      </h2>
      <p className="count">
        status: {streamState} | run:{" "}
        {selectedRunId ? shortId(selectedRunId, 12) : "-"} | raw_events:{" "}
        {rawEventCount} | messages: {conversationTail.length}
      </p>
      <div className="trace-toolbar">
        {traceView !== "conversation" && (
          <>
            <div className="trace-run-select">
              <span className="trace-label">Run</span>
              <select
                value={selectedRunId}
                onChange={(e) => setSelectedRunId(e.target.value)}
              >
                {runCandidates.map((run: any) => (
                  <option key={run.run_id} value={run.run_id}>
                    {shortId(run.run_id, 12)} ({run.event_count})
                  </option>
                ))}
              </select>
            </div>
            <div className="trace-filters">
              {(["all", "assistant", "tool", "runtime"] as const).map(
                (kind) => (
                  <button
                    key={kind}
                    type="button"
                    className={`trace-filter-btn ${eventFilter === kind ? "is-active" : ""}`}
                    onClick={() => setEventFilter(kind)}
                  >
                    {kind}
                  </button>
                ),
              )}
            </div>
          </>
        )}
        <div className="trace-view-switch">
          <button
            type="button"
            className={`trace-filter-btn ${traceView === "conversation" ? "is-active" : ""}`}
            onClick={() => setTraceView("conversation")}
          >
            conversation
          </button>
          <button
            type="button"
            className={`trace-filter-btn ${traceView === "events" ? "is-active" : ""}`}
            onClick={() => setTraceView("events")}
          >
            events
          </button>
          <button
            type="button"
            className={`trace-filter-btn ${traceView === "steps" ? "is-active" : ""}`}
            onClick={() => setTraceView("steps")}
          >
            steps
          </button>
        </div>
        <label className="trace-raw-toggle">
          <input
            type="checkbox"
            checked={showRawTable}
            onChange={(e) => setShowRawTable(e.target.checked)}
          />
          raw table
        </label>
        <label className="trace-raw-toggle">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          auto refresh
        </label>
        <button
          type="button"
          className="trace-filter-btn"
          onClick={() => {
            loadTrace(selectedRunId);
            loadConversation();
          }}
        >
          refresh
        </button>
      </div>
      {traceView === "conversation" ? (
        <div className="trace-metrics">
          <span>messages: {conversationTail.length}</span>
          <span>loading: {conversationLoading ? "yes" : "no"}</span>
        </div>
      ) : (
        <div className="trace-metrics">
          <span>assistant: {traceStats.assistant}</span>
          <span>tool: {traceStats.tool}</span>
          <span>runtime: {traceStats.runtime}</span>
          <span>loading: {traceLoading ? "yes" : "no"}</span>
        </div>
      )}
      {traceError && (
        <div className="error">Trace load failed: {traceError}</div>
      )}
      {conversationError && (
        <div className="error">
          Conversation load failed: {conversationError}
        </div>
      )}
      <div className="trace-timeline">
        {traceView === "conversation" ? (
          <>
            {conversationTail.map((message, idx) => (
              <ConversationTraceCard
                key={message?.id || `${message?.type || "msg"}-${idx}`}
                message={message}
                index={idx}
              />
            ))}
            {conversationTail.length === 0 && (
              <div className="trace-empty">No conversation messages yet.</div>
            )}
          </>
        ) : traceView === "events" ? (
          <>
            {visibleTrace.map((item, idx) => (
              <TraceCard key={`${item.seq || "na"}-${idx}`} item={item} />
            ))}
            {visibleTrace.length === 0 && (
              <div className="trace-empty">
                No trace events for this filter.
              </div>
            )}
          </>
        ) : (
          <>
            {traceSteps.map((step) => (
              <TraceStepCard
                key={`step-${step.step}-${step.seq_start || "na"}`}
                step={step}
              />
            ))}
            {traceSteps.length === 0 && (
              <div className="trace-empty">
                No trace events for this filter.
              </div>
            )}
          </>
        )}
      </div>

      {showRawTable && traceView !== "conversation" && (
        <details className="trace-raw-table" open>
          <summary>Raw trace table</summary>
          <table>
            <thead>
              <tr>
                <th>Step</th>
                <th>Actor</th>
                <th>Event</th>
                <th>Summary</th>
                <th>Run</th>
                <th>When</th>
                <th>Payload</th>
              </tr>
            </thead>
            <tbody>
              {traceTail
                .slice()
                .reverse()
                .map((item, idx) => (
                  <tr key={`${item.seq || "na"}-${idx}`}>
                    <td>{item.seq || "-"}</td>
                    <td>
                      <span className={`trace-actor trace-${item.actor}`}>
                        {item.actor}
                      </span>
                    </td>
                    <td>{item.event_type}</td>
                    <td className="mono trace-summary">{item.summary}</td>
                    <td className="mono">{shortId(item.run_id)}</td>
                    <td>{item.created_ago || "-"}</td>
                    <td>
                      <details className="trace-details">
                        <summary>view</summary>
                        <pre className="json-payload trace-payload">
                          {JSON.stringify(item.payload, null, 2)}
                        </pre>
                      </details>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </details>
      )}
    </section>
  );
}

// Page: Session Detail
function SessionDetailPage() {
  const { sessionId } = useParams();
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!sessionId) return;
    setError(null);
    fetchAPI(`/session/${sessionId}`)
      .then((payload) => setData(payload))
      .catch((e) => setError(e.message));
  }, [sessionId]);

  if (error) {
    return (
      <div className="page">
        <div className="page-error">Session load failed: {error}</div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Session: {data.session_id.slice(0, 8)}</h1>

      <section className="info-grid">
        <div>
          <strong>Thread:</strong>{" "}
          <Link to={data.thread_url}>{data.thread_id.slice(0, 8)}</Link>
        </div>
        <div>
          <strong>Status:</strong> {data.info.status}
        </div>
        <div>
          <strong>Provider:</strong> {data.info.provider || "-"}
        </div>
        <div>
          <strong>Started:</strong> {data.info.started_ago}
        </div>
        <div>
          <strong>Last Active:</strong> {data.info.last_active_ago}
        </div>
        <div>
          <strong>Ended:</strong> {data.info.ended_ago || "-"}
        </div>
      </section>

      <div className="page-tools">
        <Link className="quick-link" to={data.thread_url}>
          View thread trace
        </Link>
        {data.info.lease_id && (
          <Link className="quick-link" to={`/lease/${data.info.lease_id}`}>
            View lease
          </Link>
        )}
      </div>
    </div>
  );
}

// Page: Leases List
function LeasesPage() {
  const location = useLocation();
  const [data, setData] = React.useState<any>(null);
  const divergedOnly =
    new URLSearchParams(location.search).get("diverged") === "1";

  React.useEffect(() => {
    fetchAPI("/leases").then(setData);
  }, []);

  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }
  const triage = data.triage || {};
  const triageSummary = triage.summary || {};
  const triageGroups = Array.isArray(triage.groups) ? triage.groups : [];
  const items = divergedOnly
    ? data.items.filter((item: any) =>
        ["active_drift", "detached_residue", "orphan_cleanup"].includes(
          item.triage?.category,
        ),
      )
    : data.items;
  const visibleGroups = divergedOnly
    ? triageGroups.filter((group: any) =>
        ["active_drift", "detached_residue", "orphan_cleanup"].includes(
          group.key,
        ),
      )
    : triageGroups;

  const renderLeaseTable = (rows: any[]) => (
    <table>
      <thead>
        <tr>
          <th>Lease ID</th>
          <th>Provider</th>
          <th>Instance ID</th>
          <th>Thread</th>
          <th>State</th>
          <th>Updated</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((item: any) => (
          <tr key={item.lease_id}>
            <td>
              <Link to={item.lease_url}>{item.lease_id}</Link>
            </td>
            <td>{item.provider}</td>
            <td className="mono">{item.instance_id?.slice(0, 12) || "-"}</td>
            <td>
              {item.thread.thread_id ? (
                <Link to={item.thread.thread_url}>
                  {item.thread.thread_id.slice(0, 8)}
                </Link>
              ) : (
                <span className="orphan">orphan</span>
              )}
            </td>
            <td>
              <StateBadge badge={item.state_badge} />
            </td>
            <td>{item.updated_ago}</td>
            <td className="error">{item.error || "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <div className="page" data-testid="page-leases">
      <p className="description">
        Legacy lease view, now backed by backend triage semantics. Use this when
        you want lease-only focus without losing the full raw table.
      </p>
      <div className="resource-overview-strip">
        <span className="resource-overview-pill">
          <span className="resource-overview-label">total</span>
          <strong>
            {items.length}
            {divergedOnly ? ` / ${data.count}` : ""}
          </strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">active drift</span>
          <strong>{triageSummary.active_drift || 0}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">detached residue</span>
          <strong>{triageSummary.detached_residue || 0}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">cleanup</span>
          <strong>{triageSummary.orphan_cleanup || 0}</strong>
        </span>
        <span className="resource-overview-pill">
          <span className="resource-overview-label">healthy</span>
          <strong>{triageSummary.healthy_capacity || 0}</strong>
        </span>
      </div>
      <div className="page-tools">
        <Link
          className="quick-link"
          to={divergedOnly ? "/leases" : "/leases?diverged=1"}
        >
          {divergedOnly ? "Show all leases" : "Only attention buckets"}
        </Link>
        <Link className="quick-link" to="/resources">
          Open resources
        </Link>
      </div>
      {visibleGroups
        .filter((group: any) => group.count > 0)
        .map((group: any) => (
          <section key={group.key}>
            <h2>
              {group.title} ({group.count})
            </h2>
            <p className="description">{group.description}</p>
            {renderLeaseTable(group.items)}
          </section>
        ))}
      <details className="lease-details-shell">
        <summary>All leases ({items.length})</summary>
        {renderLeaseTable(items)}
      </details>
    </div>
  );
}

// Page: Lease Detail
function LeaseDetailPage() {
  const { leaseId } = useParams();
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setError(null);
    fetchAPI(`/lease/${leaseId}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [leaseId]);

  if (error) {
    return (
      <div className="page">
        <div className="page-error">Lease load failed: {error}</div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Lease: {data.lease_id}</h1>

      <section className="info-grid">
        <div>
          <strong>Provider:</strong> {data.info.provider}
        </div>
        <div>
          <strong>Instance ID:</strong>{" "}
          <span className="mono">{data.info.instance_id || "-"}</span>
        </div>
        <div>
          <strong>Created:</strong> {data.info.created_ago}
        </div>
        <div>
          <strong>Updated:</strong> {data.info.updated_ago}
        </div>
      </section>

      <section>
        <h2>State</h2>
        <div className="state-info">
          <div>
            <strong>Desired:</strong> {data.state.desired}
          </div>
          <div>
            <strong>Observed:</strong> {data.state.observed}
          </div>
          <div>
            <strong>Status:</strong> <StateBadge badge={data.state} />
          </div>
          {data.state.error && (
            <div className="error">
              <strong>Error:</strong> {data.state.error}
            </div>
          )}
        </div>
      </section>

      <section>
        <h2>{data.related_threads.title}</h2>
        <ul>
          {data.related_threads.items.map((t: any) => (
            <li key={t.thread_id}>
              <Link to={t.thread_url}>{t.thread_id}</Link>
            </li>
          ))}
        </ul>
        {data.related_threads.items.length === 0 && (
          <p className="count">No threads linked to this lease.</p>
        )}
      </section>

      <section>
        <h2>
          {data.lease_events.title} ({data.lease_events.count})
        </h2>
        <table>
          <thead>
            <tr>
              <th>Event ID</th>
              <th>Type</th>
              <th>Source</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {data.lease_events.items.map((e: any) => (
              <tr key={e.event_id}>
                <td>
                  <Link to={e.event_url}>{e.event_id}</Link>
                </td>
                <td>{e.event_type}</td>
                <td>{e.source}</td>
                <td>{e.created_ago}</td>
              </tr>
            ))}
            {data.lease_events.items.length === 0 && (
              <tr>
                <td colSpan={4}>No events recorded for this lease.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

// Page: Diverged Leases
function DivergedPage() {
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI("/diverged").then(setData);
  }, []);

  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="page">
      <p className="description">{data.description}</p>
      <p className="count">Total: {data.count}</p>
      <table>
        <thead>
          <tr>
            <th>Lease ID</th>
            <th>Provider</th>
            <th>Thread</th>
            <th>Desired</th>
            <th>Observed</th>
            <th>Hours Diverged</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.lease_id}>
              <td>
                <Link to={item.lease_url}>{item.lease_id}</Link>
              </td>
              <td>{item.provider}</td>
              <td>
                {item.thread.thread_id ? (
                  <Link to={item.thread.thread_url}>
                    {item.thread.thread_id.slice(0, 8)}
                  </Link>
                ) : (
                  <span className="orphan">orphan</span>
                )}
              </td>
              <td>{item.state_badge.desired}</td>
              <td>{item.state_badge.observed}</td>
              <td className={item.state_badge.color === "red" ? "error" : ""}>
                {item.state_badge.hours_diverged}h
              </td>
              <td className="error">{item.error || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Page: Events List
function EventsPage() {
  const [data, setData] = React.useState<any>(null);

  React.useEffect(() => {
    fetchAPI("/events?limit=100").then(setData);
  }, []);

  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="page">
      <p className="description">{data.description}</p>
      <p className="count">Total: {data.count}</p>
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Source</th>
            <th>Provider</th>
            <th>Lease</th>
            <th>Error</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((item: any) => (
            <tr key={item.event_id}>
              <td>
                <Link to={item.event_url}>{item.event_type}</Link>
              </td>
              <td>{item.source}</td>
              <td>{item.provider}</td>
              <td>
                {item.lease.lease_id ? (
                  <Link to={item.lease.lease_url}>{item.lease.lease_id}</Link>
                ) : (
                  "-"
                )}
              </td>
              <td className="error">{item.error || "-"}</td>
              <td>{item.created_ago}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Page: Event Detail
function EventDetailPage() {
  const { eventId } = useParams();
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setError(null);
    fetchAPI(`/event/${eventId}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [eventId]);

  if (error) {
    return (
      <div className="page">
        <div className="page-error">Event load failed: {error}</div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Event: {data.event_id}</h1>

      <section className="info-grid">
        <div>
          <strong>Type:</strong> {data.info.event_type}
        </div>
        <div>
          <strong>Source:</strong> {data.info.source}
        </div>
        <div>
          <strong>Provider:</strong> {data.info.provider}
        </div>
        <div>
          <strong>Time:</strong> {data.info.created_ago}
        </div>
      </section>

      {data.error && (
        <section>
          <h2>Error</h2>
          <pre className="json-payload error">{data.error}</pre>
        </section>
      )}

      {data.related_lease.lease_id && (
        <section>
          <h2>Related Lease</h2>
          <Link to={data.related_lease.lease_url}>
            {data.related_lease.lease_id}
          </Link>
        </section>
      )}

      <section>
        <h2>Payload</h2>
        <pre className="json-payload">
          {JSON.stringify(data.payload, null, 2)}
        </pre>
      </section>
    </div>
  );
}

// Page: Evaluation
function EvaluationPage() {
  const location = useLocation();
  const [dataset, setDataset] = React.useState("SWE-bench/SWE-bench_Lite");
  const [split, setSplit] = React.useState("test");
  const [startIdx, setStartIdx] = React.useState("0");
  const [sliceCount, setSliceCount] = React.useState("10");
  const [promptProfile, setPromptProfile] = React.useState("heuristic");
  const [timeoutSec, setTimeoutSec] = React.useState("180");
  const [recursionLimit, setRecursionLimit] = React.useState("256");
  const [sandbox, setSandbox] = React.useState("local");
  const [runStatus, setRunStatus] = React.useState<
    "idle" | "starting" | "submitted" | "error"
  >("idle");
  const [evaluationId, setEvaluationId] = React.useState("");
  const [runError, setRunError] = React.useState<string | null>(null);
  const [evaluations, setEvaluations] = React.useState<any[]>([]);
  const [evalOffset, setEvalOffset] = React.useState(0);
  const [evalLimit] = React.useState(30);
  const [evalPagination, setEvalPagination] = React.useState<any>(null);
  const [runsLoading, setRunsLoading] = React.useState(false);
  const [composerOpen, setComposerOpen] = React.useState(false);

  const loadEvaluations = React.useCallback(async () => {
    setRunsLoading(true);
    try {
      const payload = await fetchAPI(
        `/evaluations?limit=${evalLimit}&offset=${evalOffset}`,
      );
      setEvaluations(Array.isArray(payload?.items) ? payload.items : []);
      setEvalPagination(payload?.pagination || null);
    } catch (e: any) {
      setRunError(e?.message || String(e));
    } finally {
      setRunsLoading(false);
    }
  }, [evalLimit, evalOffset]);

  React.useEffect(() => {
    void loadEvaluations();
    const timer = window.setInterval(() => {
      void loadEvaluations();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadEvaluations]);

  async function handleStart() {
    if (runStatus === "starting") return;
    setRunError(null);
    setEvaluationId("");
    setRunStatus("starting");

    try {
      const payload = await fetchJSON("/api/monitor/evaluations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset,
          split,
          start: Number(startIdx),
          count: Number(sliceCount),
          prompt_profile: promptProfile,
          timeout_sec: Number(timeoutSec),
          recursion_limit: Number(recursionLimit),
          sandbox,
          arm: "monitor",
        }),
      });
      const nextEvalId = String(payload?.evaluation_id || "");
      if (!nextEvalId)
        throw new Error("create evaluation returned empty evaluation_id");
      setEvaluationId(nextEvalId);
      setRunStatus("submitted");
      setComposerOpen(false);
      await loadEvaluations();
    } catch (e: any) {
      setRunStatus("error");
      setRunError(e?.message || String(e));
    }
  }

  const currentEval = evaluations.find(
    (item: any) => item.evaluation_id === evaluationId,
  );
  const submissionPreview = {
    dataset,
    split,
    start: Number(startIdx || "0"),
    count: Number(sliceCount || "0"),
    prompt_profile: promptProfile,
    timeout_sec: Number(timeoutSec || "0"),
    recursion_limit: Number(recursionLimit || "0"),
    sandbox,
    arm: "monitor",
  };
  const parameterReference = [
    [
      "Dataset",
      "Benchmark source",
      "Lite for fast iteration, Verified for strict runs",
    ],
    ["Split", "Data partition", "Use test for formal comparison"],
    ["Start / Slice", "Case range", "Run small slices first, then scale up"],
    [
      "Prompt Profile",
      "Prompt strategy",
      "Compare baseline vs heuristic in A/B",
    ],
    ["Timeout(s)", "Per-case wall clock limit", "180~300 for initial runs"],
    [
      "Recursion",
      "Agent iteration budget",
      "256 default, raise to 512 for hard tasks",
    ],
    [
      "Sandbox",
      "Execution provider",
      "Use local for quick checks, daytona for infra parity",
    ],
  ];
  const currentProgress = currentEval ? evalProgress(currentEval) : null;

  React.useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, []);
  React.useEffect(() => {
    // @@@evaluation-query-open - allow deterministic screenshot/review entry to open config panel via ?new=1.
    const query = new URLSearchParams(location.search);
    setComposerOpen(query.get("new") === "1");
  }, [location.search]);

  return (
    <div className="page">
      <section className="eval-split-layout">
        <div className="eval-split-aside depth-recessed">
          <h2>Current Submission</h2>
          <div className="chip-row">
            <span className={`status-chip ${currentEval ? evaluationStatusTone(currentEval) : "chip-muted"}`}>
              {String(currentEval?.status || runStatus || "idle").toUpperCase()}
            </span>
          </div>
          <div className="mono">evaluation: {evaluationId || "-"}</div>
          {currentEval && currentProgress && (
            <div className="eval-runtime-panel">
              <div className="mono">
                phase: {String(currentEval.status || "-").toUpperCase()}
              </div>
              <div className="eval-progress-track">
                <div
                  className="eval-progress-fill"
                  style={{ width: `${currentProgress.pct.toFixed(1)}%` }}
                />
              </div>
              <div className="mono eval-progress-line">
                {formatProgressSummary(currentProgress)}
              </div>
            </div>
          )}
          {runError && <div className="error">run error: {runError}</div>}
          {evaluationId && (
            <p className="count">
              <Link to={`/evaluation/${evaluationId}`}>
                open evaluation detail
              </Link>
            </p>
          )}
        </div>
        <section className="eval-split-main depth-primary">
        <div className="section-row">
          <h2>Evaluations ({evalPagination?.total ?? evaluations.length})</h2>
          <span className="count">auto refresh 5s</span>
        </div>
        <div className="count evaluation-meta-row">
          <span>{evalPagination?.total ?? evaluations.length} evaluations</span>
          <span>{runsLoading ? "loading..." : "idle"}</span>
          <span>page {evalPagination?.page ?? 1}</span>
        </div>
        <table>
          <thead>
            <tr>
              <th title="Unique evaluation id">Evaluation</th>
              <th title="Benchmark dataset id">Dataset</th>
              <th title="Case index range inside selected split">Range</th>
              <th title="prompt_profile / sandbox">Profile / Sandbox</th>
              <th title="queued / running / completed / completed_with_errors / error">
                Status
              </th>
              <th title="total / completed / started|in-progress / pending / progress%">
                Progress
              </th>
              <th title="resolved / total from SWE-bench summary">Score</th>
              <th title="Last persisted status update">Updated</th>
            </tr>
          </thead>
          <tbody>
            {evaluations.map((item: any) => (
              <tr key={item.evaluation_id}>
                <td>
                  <Link to={item.evaluation_url}>
                    {shortId(item.evaluation_id, 14)}
                  </Link>
                </td>
                <td className="mono">{item.dataset}</td>
                <td>
                  {item.start_idx}..{item.start_idx + item.slice_count - 1}
                </td>
                <td className="mono">
                  {item.prompt_profile || "-"} / {item.sandbox || "-"}
                </td>
                <td>
                  {(() => {
                    return (
                      <div className="eval-status-stack">
                        <span className={`status-chip ${evaluationStatusTone(item)}`}>
                          {String(item.status || "-").toUpperCase()}
                        </span>
                        <span
                          className={`status-chip ${Boolean(item.score?.publishable ?? item.score?.score_gate === "final") ? "chip-success" : "chip-muted"}`}
                        >
                          {Boolean(item.score?.publishable ?? item.score?.score_gate === "final")
                            ? "publishable"
                            : "provisional"}
                        </span>
                      </div>
                    );
                  })()}
                </td>
                <td>
                  {(() => {
                    const p = evalProgress(item);
                    return (
                      <div className="eval-progress-cell">
                        <div className="eval-progress-track">
                          <div
                            className="eval-progress-fill"
                            style={{ width: `${p.pct.toFixed(1)}%` }}
                          />
                        </div>
                        <div className="mono eval-progress-line">
                          {formatProgressSummary(p)}
                        </div>
                      </div>
                    );
                  })()}
                </td>
                <td className="mono">
                  <div className="eval-score-stack">
                    <span className={`status-chip ${evaluationScoreTone(item)}`}>
                      {(item.score?.publishable ?? item.score?.score_gate === "final")
                        ? `R ${formatResolvedScore(item)}`
                        : "R PROVISIONAL"}
                    </span>
                    <div>
                      C {formatPct(item.score?.completed_rate_pct)} | T{" "}
                      {formatPct(item.score?.tool_call_thread_rate_pct)}
                    </div>
                  </div>
                </td>
                <td>{item.updated_ago || "-"}</td>
              </tr>
            ))}
            {evaluations.length === 0 && (
              <tr>
                <td colSpan={8}>No evaluations yet.</td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="evaluation-pagination-row">
          <div className="count evaluation-pagination-copy">
            offset={evalPagination?.offset ?? 0} | limit=
            {evalPagination?.limit ?? evalLimit} | total=
            {evalPagination?.total ?? evaluations.length}
          </div>
          <div className="evaluation-pagination-actions">
            <button
              className="ghost-btn"
              onClick={() =>
                setEvalOffset(Math.max(evalPagination?.prev_offset ?? 0, 0))
              }
              disabled={!evalPagination?.has_prev || runsLoading}
            >
              Prev
            </button>
            <button
              className="ghost-btn"
              onClick={() =>
                setEvalOffset(
                  evalPagination?.next_offset ?? evalOffset + evalLimit,
                )
              }
              disabled={!evalPagination?.has_next || runsLoading}
            >
              Next
            </button>
          </div>
        </div>
        </section>
      </section>

      {composerOpen && (
        // @@@evaluation-composer-modal - keep config editing in a fixed layer to avoid "tail jump" in long list pages.
        <div
          className="eval-composer-backdrop"
          onClick={() => setComposerOpen(false)}
        >
          <section
            className="eval-composer-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="section-row">
              <h2>New Evaluation Config</h2>
              <button
                className="ghost-btn"
                onClick={() => setComposerOpen(false)}
                disabled={runStatus === "starting"}
              >
                Close
              </button>
            </div>
            <p className="description">
              Configure run scope, profile and runtime, then submit.
            </p>

            <section className="evaluation-layout">
              <div className="evaluation-column">
                <h2>Run Scope</h2>
                <div className="info-grid evaluation-grid">
                  <div className="field-group">
                    <label className="field-label">
                      <strong>Dataset</strong>
                    </label>
                    <select
                      value={dataset}
                      onChange={(e) => setDataset(e.target.value)}
                    >
                      <option value="SWE-bench/SWE-bench_Lite">
                        SWE-bench/SWE-bench_Lite
                      </option>
                      <option value="princeton-nlp/SWE-bench_Verified">
                        princeton-nlp/SWE-bench_Verified
                      </option>
                    </select>
                    <p className="field-help">
                      Benchmark source. Lite is faster; Verified is stricter and
                      slower.
                    </p>
                  </div>
                  <div className="field-group">
                    <label className="field-label">
                      <strong>Split</strong>
                    </label>
                    <select
                      value={split}
                      onChange={(e) => setSplit(e.target.value)}
                    >
                      <option value="test">test</option>
                      <option value="dev">dev</option>
                    </select>
                    <p className="field-help">
                      Dataset partition. Use <span className="mono">test</span>{" "}
                      for formal comparison.
                    </p>
                  </div>
                  <div className="field-group">
                    <label className="field-label">
                      <strong>Start</strong>
                    </label>
                    <input
                      value={startIdx}
                      onChange={(e) => setStartIdx(e.target.value)}
                    />
                    <p className="field-help">
                      Starting index inside the selected split.
                    </p>
                  </div>
                  <div className="field-group">
                    <label className="field-label">
                      <strong>Slice</strong>
                    </label>
                    <select
                      value={sliceCount}
                      onChange={(e) => setSliceCount(e.target.value)}
                    >
                      <option value="5">5</option>
                      <option value="10">10</option>
                      <option value="20">20</option>
                    </select>
                    <p className="field-help">
                      How many items to run in this evaluation batch.
                    </p>
                  </div>
                </div>
              </div>

              <div className="evaluation-column">
                <h2>Agent Profile</h2>
                <div className="info-grid evaluation-grid">
                  <div className="field-group">
                    <label className="field-label">
                      <strong>Prompt Profile</strong>
                    </label>
                    <select
                      value={promptProfile}
                      onChange={(e) => setPromptProfile(e.target.value)}
                    >
                      <option value="baseline">baseline</option>
                      <option value="heuristic">heuristic</option>
                    </select>
                    <p className="field-help">
                      Prompt strategy passed to runner. Used for A/B profile
                      comparison.
                    </p>
                  </div>
                  <div className="field-group">
                    <label className="field-label">
                      <strong>Recursion</strong>
                    </label>
                    <input
                      value={recursionLimit}
                      onChange={(e) => setRecursionLimit(e.target.value)}
                    />
                    <p className="field-help">
                      Agent recursion/iteration budget per item.
                    </p>
                  </div>
                </div>
              </div>

              <div className="evaluation-column">
                <h2>Runtime</h2>
                <div className="info-grid evaluation-grid">
                  <div className="field-group">
                    <label className="field-label">
                      <strong>Timeout(s)</strong>
                    </label>
                    <input
                      value={timeoutSec}
                      onChange={(e) => setTimeoutSec(e.target.value)}
                    />
                    <p className="field-help">
                      Per-item wall-clock timeout in seconds.
                    </p>
                  </div>
                  <div className="field-group">
                    <label className="field-label">
                      <strong>Sandbox</strong>
                    </label>
                    <select
                      value={sandbox}
                      onChange={(e) => setSandbox(e.target.value)}
                    >
                      <option value="local">local</option>
                      <option value="daytona">daytona</option>
                    </select>
                    <p className="field-help">
                      Execution environment provider for this run.
                    </p>
                  </div>
                </div>
              </div>

              <div className="evaluation-column evaluation-column-action">
                <div className="evaluation-action-row">
                  <button
                    className="primary-btn"
                    onClick={handleStart}
                    disabled={runStatus === "starting" || !startIdx.trim()}
                  >
                    {runStatus === "starting" ? "Starting..." : "Start Eval"}
                  </button>
                  <button
                    className="ghost-btn"
                    onClick={() => setComposerOpen(false)}
                    disabled={runStatus === "starting"}
                  >
                    Cancel
                  </button>
                </div>
                <p className="field-help">
                  Submits config to backend and starts an evaluation job.
                </p>
              </div>
            </section>

            <details className="trace-details">
              <summary>Submission Preview</summary>
              <pre className="json-payload">
                {JSON.stringify(submissionPreview, null, 2)}
              </pre>
            </details>

            <details className="trace-details">
              <summary>Parameter Reference</summary>
              <table>
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Meaning</th>
                    <th>Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {parameterReference.map((row) => (
                    <tr key={row[0]}>
                      <td>{row[0]}</td>
                      <td>{row[1]}</td>
                      <td>{row[2]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </section>
        </div>
      )}
    </div>
  );
}

function EvaluationDetailPage() {
  const { evaluationId } = useParams();
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setError(null);
    fetchAPI(`/evaluation/${evaluationId}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [evaluationId]);

  if (error) {
    return (
      <div className="page">
        <div className="page-error">Evaluation load failed: {error}</div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="page">
        <div className="page-loading">Loading...</div>
      </div>
    );
  }
  const detailProgress = evalProgress({
    threads_done: data.info?.threads_done ?? 0,
    threads_running: data.info?.threads_running ?? 0,
    slice_count: data.info?.slice_count ?? data.info?.threads_total ?? 0,
    progress_source: data.info?.progress_source ?? "thread_rows",
  });
  const threadStateLabel =
    detailProgress.mode === "checkpoint_estimate" ? "started" : "running";
  const scoreGate = String(data.info?.score?.score_gate || "provisional");
  const publishable = Boolean(
    data.info?.score?.publishable ?? scoreGate === "final",
  );
  const scoreFinal = publishable;
  const summaryReady = !!data.info?.score?.eval_summary_path;
  const operator = data.info?.operator_surface || {};
  const statusToneClass =
    data.info.status === "completed"
      ? "chip-success"
      : data.info.status === "error"
        ? "chip-danger"
        : data.info.status === "provisional" ||
            data.info.status === "completed_with_errors"
          ? "chip-warning"
          : "";

  return (
    <div className="page">
      <Breadcrumb items={data.breadcrumb} />
      <h1>Evaluation: {shortId(data.evaluation_id, 14)}</h1>
      <div className="eval-summary-bar">
        <span className={`eval-summary-chip ${statusToneClass}`.trim()}>
          {data.info.status}
        </span>
        <span className="eval-summary-chip mono">{data.info.dataset}</span>
        <span className="eval-summary-chip">
          {threadStateLabel}={data.info.threads_running}/
          {data.info.threads_total}
        </span>
        <span className="eval-summary-chip">gate={scoreGate}</span>
        <span
          className={`eval-summary-chip ${publishable ? "chip-success" : "chip-warning"}`}
        >
          publishable={String(publishable)}
        </span>
        <span className="eval-summary-chip">
          score=
          {scoreFinal
            ? `${data.info.score?.resolved_instances ?? 0}/${data.info.score?.total_instances ?? 0} (${formatPct(data.info.score?.primary_score_pct)})`
            : "PROVISIONAL"}
        </span>
      </div>
      <section className="eval-runtime-panel">
        <div className="mono">
          phase: {String(data.info.status || "-").toUpperCase()}
        </div>
        <div className="eval-progress-track">
          <div
            className="eval-progress-fill"
            style={{ width: `${detailProgress.pct.toFixed(1)}%` }}
          />
        </div>
        <div className="mono eval-progress-line">
          {formatProgressSummary(detailProgress)}
        </div>
      </section>

      <section
        className={`eval-operator-shell eval-operator-${operator.tone || "default"}`}
        data-testid="evaluation-operator-surface"
      >
        <div className="eval-operator-hero">
          <div>
            <h2>Operator Status</h2>
            <p className="description">
              {operator.summary ||
                "Inspect the current evaluation state before judging score or trace coverage."}
            </p>
          </div>
          <span
            className={`status-chip ${operator.tone === "danger" ? "chip-danger" : operator.tone === "warning" ? "chip-warning" : operator.tone === "success" ? "chip-success" : "chip-muted"}`}
          >
            {operator.tone || "default"}
          </span>
        </div>
        <strong className="eval-operator-headline">
          {operator.headline || "Evaluation operator surface"}
        </strong>
        <div className="eval-operator-grid">
          <article className="hint-box">
            <h3>Facts</h3>
            <div className="info-grid info-grid-compact">
              {(operator.facts || []).map((item: any) => (
                <div key={`${item.label}:${item.value}`}>
                  <strong>{item.label}:</strong> {item.value}
                </div>
              ))}
            </div>
          </article>
          <article className="hint-box">
            <h3>Artifacts</h3>
            <ul className="eval-artifact-list">
              {(operator.artifacts || []).map((item: any) => (
                <li key={`${item.label}:${item.path}`}>
                  <strong>{item.label}:</strong>{" "}
                  <span className="mono">{item.path}</span>
                </li>
              ))}
            </ul>
          </article>
        </div>
        <article className="hint-box">
          <h3>Next Step</h3>
          <ol className="eval-next-step-list">
            {(operator.next_steps || []).map((item: string) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </article>
        {operator.raw_notes ? (
          <details className="eval-raw-notes">
            <summary>Raw runner notes</summary>
            <pre className="mono">{operator.raw_notes}</pre>
          </details>
        ) : null}
      </section>

      <section>
        <h2>Config</h2>
        <div className="info-grid info-grid-compact">
          <div>
            <strong>Split:</strong> {data.info.split}
          </div>
          <div>
            <strong>Start:</strong> {data.info.start_idx}
          </div>
          <div>
            <strong>Count:</strong> {data.info.slice_count}
          </div>
          <div>
            <strong>Profile:</strong> {data.info.prompt_profile}
          </div>
          <div>
            <strong>Timeout:</strong> {data.info.timeout_sec}s
          </div>
          <div>
            <strong>Recursion:</strong> {data.info.recursion_limit}
          </div>
        </div>
      </section>

      {scoreFinal ? (
        <section>
          <h2>Score</h2>
          <div className="info-grid">
            <div>
              <strong>Score Gate:</strong> {scoreGate}
            </div>
            <div>
              <strong>Publishable:</strong> {String(publishable)}
            </div>
            <div>
              <strong>Summary:</strong> {summaryReady ? "ready" : "missing"}
            </div>
            <div>
              <strong>Resolved:</strong>{" "}
              {data.info.score?.resolved_instances ?? 0}/
              {data.info.score?.total_instances ?? 0}
            </div>
            <div>
              <strong>Resolved Rate:</strong>{" "}
              {formatPct(data.info.score?.resolved_rate_pct)}
            </div>
            <div>
              <strong>Completed:</strong>{" "}
              {data.info.score?.completed_instances ?? 0}/
              {data.info.score?.total_instances ?? 0}
            </div>
            <div>
              <strong>Completed Rate:</strong>{" "}
              {formatPct(data.info.score?.completed_rate_pct)}
            </div>
            <div>
              <strong>Non-empty Patch:</strong>{" "}
              {data.info.score?.non_empty_patch_instances ?? 0}/
              {data.info.score?.total_instances ?? 0}
            </div>
            <div>
              <strong>Non-empty Rate:</strong>{" "}
              {formatPct(data.info.score?.non_empty_patch_rate_pct)}
            </div>
            <div>
              <strong>Empty Patch:</strong>{" "}
              {data.info.score?.empty_patch_instances ?? 0}/
              {data.info.score?.total_instances ?? 0}
            </div>
            <div>
              <strong>Errors:</strong> {data.info.score?.error_instances ?? 0}
            </div>
            <div>
              <strong>Trace Active:</strong>{" "}
              {data.info.score?.active_trace_threads ?? 0}/
              {data.info.score?.total_instances ?? 0}
            </div>
            <div>
              <strong>Tool-call Threads:</strong>{" "}
              {data.info.score?.tool_call_threads ?? 0}/
              {data.info.score?.total_instances ?? 0}
            </div>
            <div>
              <strong>Tool-call Coverage:</strong>{" "}
              {formatPct(data.info.score?.tool_call_thread_rate_pct)}
            </div>
            <div>
              <strong>Tool Calls Total:</strong>{" "}
              {data.info.score?.tool_calls_total ?? 0}
            </div>
            <div>
              <strong>Avg Tool Calls(active):</strong>{" "}
              {data.info.score?.avg_tool_calls_per_active_thread ?? "-"}
            </div>
            <div>
              <strong>Recursion Cap Hits:</strong>{" "}
              {data.info.score?.recursion_cap_hits ?? 0}
              {data.info.score?.recursion_limit
                ? ` / cap ${data.info.score.recursion_limit}`
                : ""}
            </div>
            <div>
              <strong>Run Dir:</strong>{" "}
              <span className="mono">{data.info.score?.run_dir || "-"}</span>
            </div>
          </div>
        </section>
      ) : (
        <details className="eval-score-details">
          <summary>Score artifacts (provisional)</summary>
          <div className="info-grid">
            <div>
              <strong>Score Gate:</strong> {scoreGate}
            </div>
            <div>
              <strong>Publishable:</strong> {String(publishable)}
            </div>
            <div>
              <strong>Summary:</strong> {summaryReady ? "ready" : "missing"}
            </div>
            <div>
              <strong>Final Score:</strong> blocked (provisional)
            </div>
            <div>
              <strong>Block Reason:</strong>{" "}
              {data.info.score?.manifest_eval_error
                ? "manifest_eval_error"
                : "missing_eval_summary"}
            </div>
            <div>
              <strong>Run Dir:</strong>{" "}
              <span className="mono">{data.info.score?.run_dir || "-"}</span>
            </div>
          </div>
        </details>
      )}

      <section>
        <h2>
          {data.threads.title} ({data.threads.count})
        </h2>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Thread</th>
              <th>Session</th>
              <th>Run</th>
              <th>Events</th>
              <th>Status</th>
              <th>Start</th>
            </tr>
          </thead>
          <tbody>
            {data.threads.items.map((item: any) => (
              <tr key={item.thread_id}>
                <td>{item.item_index}</td>
                <td>
                  <Link to={item.thread_url} title={item.thread_id}>
                    <span className="mono">
                      {evalThreadLabel(item.thread_id, data.evaluation_id)}
                    </span>
                  </Link>
                </td>
                <td>
                  {item.session?.session_url ? (
                    <Link to={item.session.session_url}>
                      {shortId(item.session.session_id)}
                    </Link>
                  ) : (
                    "-"
                  )}
                </td>
                <td className="mono">
                  {item.run?.run_id ? shortId(item.run.run_id, 12) : "-"}
                </td>
                <td>{item.run?.event_count ?? 0}</td>
                <td>{item.status}</td>
                <td>{item.start_idx}</td>
              </tr>
            ))}
            {data.threads.items.length === 0 && (
              <tr>
                <td colSpan={7}>No threads in this evaluation.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

// @@@nav-information-architecture - grouped rail: overview → infra → workload. Section headers add hierarchy without adding pages.
const SHELL_NAV_GROUPS = [
  {
    label: "Overview",
    items: [
      { to: "/dashboard", label: "Dashboard", shortLabel: "DB", testId: "nav-dashboard" },
    ],
  },
  {
    label: "Infrastructure",
    items: [
      { to: "/resources", label: "Resources", shortLabel: "RS", testId: "nav-resources" },
      { to: "/leases", label: "Leases", shortLabel: "LS", testId: "nav-leases" },
    ],
  },
  {
    label: "Workload",
    items: [
      { to: "/evaluation", label: "Evaluations", shortLabel: "EV", testId: "nav-eval" },
      { to: "/threads", label: "Threads", shortLabel: "TH", testId: "nav-threads" },
      { to: "/traces", label: "Traces", shortLabel: "TR", testId: "nav-traces" },
    ],
  },
] as const;

const GUIDE_SECTIONS = [
  {
    title: "Dashboard",
    body: "Start here. Read provider health, live workload pressure, and the latest evaluation before drilling into detail.",
  },
  {
    title: "Resources",
    body: "Use the global resources page to inspect provider health, select a lease, and then narrow the session truth surface without losing the global contract.",
  },
  {
    title: "Evaluations",
    body: "Open config only when you are ready to submit. After that, stay in the list or jump into evaluation detail for artifacts, trace, and next-step diagnosis.",
  },
  {
    title: "Threads / Traces / Leases",
    body: "Treat these as truth surfaces. Use them when the dashboard or resources page tells you where to look, not as the first page you land on.",
  },
] as const;

function shellMeta(pathname: string): { title: string; subtitle: string } {
  // @@@shell-route-bucketing - detail routes inherit the nearest console section.
  if (pathname.startsWith("/resources") || pathname.startsWith("/lease"))
    return { title: "Resources", subtitle: "Provider health · lease triage · session truth" };
  if (pathname.startsWith("/evaluation"))
    return { title: "Evaluations", subtitle: "Submit · track · inspect artifacts" };
  if (pathname.startsWith("/threads") || pathname.startsWith("/thread"))
    return { title: "Threads", subtitle: "Global thread index · session and trace drill-down" };
  if (pathname.startsWith("/traces") || pathname.startsWith("/session"))
    return { title: "Traces", subtitle: "Sequence-level session and tool-call inspection" };
  if (pathname.startsWith("/events") || pathname.startsWith("/event"))
    return { title: "Events", subtitle: "Lease and runtime event history" };
  if (pathname.startsWith("/leases"))
    return { title: "Leases", subtitle: "Grouped triage · raw truth fallback" };
  return { title: "Dashboard", subtitle: "Health · workload · latest evaluation" };
}

function OperatorGuideModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="shell-modal-backdrop"
      onClick={onClose}
      data-testid="operator-guide-modal"
    >
      <section
        className="shell-modal-panel"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="section-row shell-modal-head">
          <div>
            <p className="shell-eyebrow">Operator Guide</p>
            <h2>How to read this console</h2>
          </div>
          <button className="ghost-btn" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="description">
          This guide stays out of the main content column by default. Open it
          when you need orientation, then go back to the live console surface.
        </p>
        <div className="shell-guide-grid">
          {GUIDE_SECTIONS.map((section) => (
            <article key={section.title} className="hint-box">
              <h2>{section.title}</h2>
              <p className="description">{section.body}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function ScrollToTopOnRouteChange() {
  const { pathname } = useLocation();
  React.useEffect(() => {
    // @@@history-scroll-restore-disable - browser may restore stale scroll offsets and make user land at page tail.
    const prev = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    return () => {
      window.history.scrollRestoration = prev;
    };
  }, []);
  React.useEffect(() => {
    // @@@route-scroll-reset - switch tabs/details should always start from top to avoid "tail landing" confusion.
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname]);
  return null;
}

function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const [guideOpen, setGuideOpen] = React.useState(false);
  const meta = shellMeta(pathname);
  const showEvalComposeAction = pathname === "/evaluation";

  return (
    <div className="console-app">
      <aside className="console-sidebar" data-testid="monitor-nav">
        <div className="console-brand">
          <div className="console-brand-mark">M</div>
          <div>
            <strong className="logo">Mycel Monitor</strong>
            <p className="console-brand-copy">Sandbox Console</p>
          </div>
        </div>
        <nav className="console-nav">
          {SHELL_NAV_GROUPS.map((group) => (
            <div key={group.label} className="console-nav-group">
              <span className="console-nav-group-label">{group.label}</span>
              {group.items.map((item) => (
                <NavLink key={item.to} data-testid={item.testId} to={item.to}>
                  <span className="console-nav-mark" aria-hidden="true">
                    {item.shortLabel}
                  </span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="console-sidebar-foot">
          <div className="console-foot-row">
            <span className="console-foot-dot" />
            <span>Monitor</span>
          </div>
          <span className="console-foot-meta">global · light · v0</span>
        </div>
      </aside>
      <div className="console-main">
        <header className="console-header">
          <div>
            <h1 className="console-title">{meta.title}</h1>
            <p className="console-subtitle">{meta.subtitle}</p>
          </div>
          <div className="console-header-actions">
            {showEvalComposeAction ? (
              <Link className="primary-btn" to="/evaluation?new=1">
                Build Eval
              </Link>
            ) : null}
            <button
              className="ghost-btn"
              onClick={() => setGuideOpen(true)}
              data-testid="operator-guide-trigger"
            >
              Operator Guide
            </button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
      <OperatorGuideModal
        open={guideOpen}
        onClose={() => setGuideOpen(false)}
      />
    </div>
  );
}

// Main App
export default function App() {
  return (
    <BrowserRouter>
      <ScrollToTopOnRouteChange />
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/threads" element={<ThreadsPage />} />
          <Route path="/resources" element={<MonitorResourcesPage />} />
          <Route path="/traces" element={<TracesPage />} />
          <Route path="/thread/:threadId" element={<ThreadDetailPage />} />
          <Route path="/session/:sessionId" element={<SessionDetailPage />} />
          <Route path="/leases" element={<LeasesPage />} />
          <Route path="/lease/:leaseId" element={<LeaseDetailPage />} />
          <Route
            path="/diverged"
            element={<Navigate to="/leases?diverged=1" replace />}
          />
          <Route path="/events" element={<EventsPage />} />
          <Route path="/event/:eventId" element={<EventDetailPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route
            path="/evaluation/:evaluationId"
            element={<EvaluationDetailPage />}
          />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
