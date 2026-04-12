import React from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Camera,
  Cpu,
  FolderOpen,
  Globe,
  HardDrive,
  Terminal,
  Webhook,
} from "lucide-react";

import {
  browseMonitorSandbox,
  cleanupMonitorProviderSession,
  fetchJsonOrThrow,
  fetchMonitorProviderSessions,
  fetchMonitorResources,
  readMonitorSandboxFile,
  refreshMonitorResources,
} from "./resources/api";
import { cx } from "./app/classes";
import type {
  BrowseItem,
  ProviderCapabilities,
  ProviderInfo,
  ProviderOrphanSession,
  ResourceOverviewResponse,
  ResourceSession,
  SessionMetrics,
} from "./resources/types";

const PROVIDER_TYPE_LABEL = {
  local: "本地",
  cloud: "云端",
  container: "容器",
} as const;

const CAPABILITY_LABELS: Record<keyof ProviderCapabilities, string> = {
  filesystem: "文件",
  terminal: "终端",
  metrics: "指标",
  screenshot: "截屏",
  web: "Web",
  process: "进程",
  hooks: "Hook",
  mount: "挂载",
};

const CAPABILITY_ICON_MAP: Record<keyof ProviderCapabilities, React.ElementType> = {
  filesystem: FolderOpen,
  terminal: Terminal,
  metrics: Activity,
  screenshot: Camera,
  web: Globe,
  process: Cpu,
  hooks: Webhook,
  mount: HardDrive,
};

const STATUS_LABEL = {
  active: "活跃",
  ready: "就绪",
  unavailable: "未就绪",
  running: "运行中",
  paused: "已暂停",
  stopped: "已结束",
  destroying: "销毁中",
} as const;

const SESSION_STATUS_ORDER: Record<ResourceSession["status"], number> = {
  running: 0,
  destroying: 1,
  paused: 2,
  stopped: 3,
};
const SANDBOX_FILTER_STATUSES: ResourceSession["status"][] = ["running", "paused", "stopped", "destroying"];

interface LeaseGroup {
  leaseId: string;
  status: ResourceSession["status"];
  sessions: ResourceSession[];
  startedAt: string;
  metrics: SessionMetrics | null;
}

const AGENT_FALLBACK_COLORS = [
  "#dbeafe:#1d4ed8",
  "#dcfce7:#15803d",
  "#f3e8ff:#7e22ce",
  "#ffedd5:#c2410c",
  "#fce7f3:#be185d",
  "#ccfbf1:#0f766e",
] as const;

function avatarColor(name: string): { backgroundColor: string; color: string } {
  let hash = 0;
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash * 31 + name.charCodeAt(index)) | 0;
  }
  const [backgroundColor, color] = AGENT_FALLBACK_COLORS[Math.abs(hash) % AGENT_FALLBACK_COLORS.length].split(":");
  return { backgroundColor, color };
}

function formatNumber(value: number | null | undefined): string {
  if (value == null) {
    return "--";
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(1).replace(/\.0$/, "");
}

function formatMetric(value: number | null | undefined, unit: string): string {
  if (value == null) return "--";
  if (unit === "GB" && value > 0 && value < 1) {
    return `${Math.round(value * 1024)}MB`;
  }
  return `${formatNumber(value)}${unit}`;
}

function formatSessionMetricRange(used: number | null | undefined, limit: number | null | undefined, unit: string): string {
  if (used == null && limit == null) {
    return "--";
  }
  if (used != null && limit != null) {
    return `${formatMetric(used, unit)} / ${formatMetric(limit, unit)}`;
  }
  if (used != null) {
    return formatMetric(used, unit);
  }
  return `limit ${formatMetric(limit, unit)}`;
}

function calculateDuration(createdAt: string): number | null {
  const startedAt = new Date(createdAt).getTime();
  if (Number.isNaN(startedAt)) {
    return null;
  }

  const elapsed = Date.now() - startedAt;
  return elapsed >= 0 ? elapsed : null;
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}天${hours % 24}小时`;
  if (hours > 0) return `${hours}小时${minutes % 60}分`;
  if (minutes > 0) return `${minutes}分${seconds % 60}秒`;
  return `${seconds}秒`;
}

function formatStartedAtDuration(createdAt: string | null | undefined): string {
  if (!createdAt) {
    return "--";
  }

  const elapsed = calculateDuration(createdAt);
  return elapsed == null ? "时间异常" : formatDuration(elapsed);
}

function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  return trimmed
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 2);
}

function MonitorAvatar({
  name,
  avatarUrl,
  size = "sm",
  count,
}: {
  name: string;
  avatarUrl?: string | null;
  size?: "sm" | "lg";
  count?: number;
}) {
  if (typeof count === "number") {
    return (
      <div className="sandbox-avatar sandbox-avatar--count" aria-label={`${count} more agents`}>
        +{count}
      </div>
    );
  }

  const sizeClass = size === "lg" ? "sandbox-avatar--lg" : "";
  const fallbackStyle = avatarColor(name || "?");

  return (
    <div
      className={cx("sandbox-avatar", sizeClass)}
      title={name || "未绑定"}
      aria-label={`${name || "未绑定"} avatar`}
      style={!avatarUrl ? fallbackStyle : undefined}
    >
      {avatarUrl ? <img src={avatarUrl} alt="" /> : initials(name || "未绑定")}
    </div>
  );
}

const PROVIDER_TYPE_GLYPH = {
  local: "◉",
  cloud: "☁",
  container: "▣",
} as const;

function groupByLease(sessions: ResourceSession[]): LeaseGroup[] {
  const map = new Map<string, ResourceSession[]>();
  for (const session of sessions) {
    const key = session.leaseId || session.id;
    const rows = map.get(key) ?? [];
    rows.push(session);
    map.set(key, rows);
  }

  return Array.from(map.values())
    .map((group) => {
      const sorted = [...group].sort(
        (left, right) => (SESSION_STATUS_ORDER[left.status] ?? 4) - (SESSION_STATUS_ORDER[right.status] ?? 4),
      );
      const best = sorted[0];
      const earliest = group.reduce(
        (min, session) => (session.startedAt < min ? session.startedAt : min),
        group[0].startedAt,
      );
      return {
        leaseId: group[0].leaseId ?? "",
        status: best.status,
        sessions: sorted,
        startedAt: earliest,
        metrics: best.metrics ?? null,
      } satisfies LeaseGroup;
    })
    .sort((left, right) => (SESSION_STATUS_ORDER[left.status] ?? 4) - (SESSION_STATUS_ORDER[right.status] ?? 4));
}

function defaultProviderStatusFilter(groups: LeaseGroup[]): LeaseGroup["status"] | "all" {
  if (groups.some((group) => group.status === "running")) {
    return "running";
  }
  if (groups.some((group) => group.status === "paused")) {
    return "paused";
  }
  return "all";
}

function countSessions(sessions: ResourceSession[], status: ResourceSession["status"]): number {
  return sessions.filter((session) => session.status === status).length;
}

function countProviderSessions(providers: ProviderInfo[], status: ResourceSession["status"]): number {
  return providers.reduce((total, provider) => total + countSessions(provider.sessions, status), 0);
}

function countRuntimeUnboundRunning(provider: ProviderInfo): number {
  return provider.sessions.filter(
    (session) => provider.type !== "local" && session.status === "running" && !session.runtimeSessionId,
  ).length;
}

function countDetachedResidue(sessions: ResourceSession[]): number {
  return sessions.filter(
    (session) => session.status === "stopped" && !session.runtimeSessionId && session.metrics == null,
  ).length;
}

export default function ResourcesPage() {
  const [providers, setProviders] = React.useState<ProviderInfo[]>([]);
  const [selectedId, setSelectedId] = React.useState("");
  const [summary, setSummary] = React.useState<ResourceOverviewResponse["summary"] | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [providerOrphans, setProviderOrphans] = React.useState<ProviderOrphanSession[]>([]);
  const [providerOrphansLoading, setProviderOrphansLoading] = React.useState(false);
  const [providerOrphansError, setProviderOrphansError] = React.useState<string | null>(null);
  const [providerCleanupPendingId, setProviderCleanupPendingId] = React.useState<string | null>(null);
  const [providerCleanupMessage, setProviderCleanupMessage] = React.useState<string | null>(null);

  const applyPayload = React.useCallback((payload: ResourceOverviewResponse) => {
    setProviders(payload.providers);
    setSummary(payload.summary);
    setSelectedId((previous) => {
      if (payload.providers.some((provider) => provider.id === previous)) {
        return previous;
      }
      return payload.providers[0]?.id ?? "";
    });
  }, []);

  const loadProviderOrphans = React.useCallback(async () => {
    setProviderOrphansLoading(true);
    setProviderOrphansError(null);
    try {
      const payload = await fetchMonitorProviderSessions();
      setProviderOrphans(payload.sessions);
    } catch (exc) {
      setProviderOrphansError(exc instanceof Error ? exc.message : "Provider 运行时检查失败");
    } finally {
      setProviderOrphansLoading(false);
    }
  }, []);

  const loadSnapshot = React.useCallback(async () => {
    try {
      const payload = await fetchMonitorResources();
      applyPayload(payload);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "资源刷新失败";
      setSummary((prev) => (
        prev
          ? {
              ...prev,
              refresh_status: "error",
              refresh_error: message,
            }
          : prev
      ));
    }
  }, [applyPayload]);

  const retryLoad = React.useCallback(async () => {
    setRefreshing(true);
    try {
      const payload = await fetchMonitorResources();
      applyPayload(payload);
      setError(null);
      void loadProviderOrphans();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "资源加载失败");
    } finally {
      setRefreshing(false);
    }
  }, [applyPayload, loadProviderOrphans]);

  const refreshNow = React.useCallback(async () => {
    setRefreshing(true);
    try {
      const payload = await refreshMonitorResources();
      applyPayload(payload);
      await loadProviderOrphans();
      setError(null);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "资源刷新失败";
      if (providers.length > 0) {
        setSummary((prev) => (
          prev
            ? {
                ...prev,
                refresh_status: "error",
                refresh_error: message,
              }
            : prev
        ));
      } else {
        setError(message);
      }
    } finally {
      setRefreshing(false);
    }
  }, [applyPayload, loadProviderOrphans, providers.length]);

  const cleanupProviderOrphan = React.useCallback(
    async (session: ProviderOrphanSession) => {
      const pendingId = `${session.provider}:${session.session_id}`;
      setProviderCleanupPendingId(pendingId);
      setProviderCleanupMessage(null);
      try {
        const result = await cleanupMonitorProviderSession(session.provider, session.session_id);
        setProviderCleanupMessage(result.message ?? "Provider 运行时清理已完成");
        await loadProviderOrphans();
      } catch (exc) {
        setProviderCleanupMessage(exc instanceof Error ? exc.message : "Provider 运行时清理失败");
      } finally {
        setProviderCleanupPendingId(null);
      }
    },
    [loadProviderOrphans],
  );

  React.useEffect(() => {
    let cancelled = false;

    async function loadInitial() {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchMonitorResources();
        if (!cancelled) {
          applyPayload(payload);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "资源加载失败");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadInitial();
    void loadProviderOrphans();
    return () => {
      cancelled = true;
    };
  }, [applyPayload, loadProviderOrphans]);

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      void loadSnapshot();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [loadSnapshot]);

  const selected = providers.find((provider) => provider.id === selectedId) ?? null;
  const selectedProviderOrphans = selected ? providerOrphans.filter((session) => session.provider === selected.id) : [];
  const runningSessionCount = countProviderSessions(providers, "running");
  const pausedSessionCount = countProviderSessions(providers, "paused");
  const stoppedSessionCount = countProviderSessions(providers, "stopped");
  const leaseGroupCount = providers.reduce((total, provider) => total + groupByLease(provider.sessions).length, 0);
  const refreshedAt = summary?.last_refreshed_at
    ? new Date(summary.last_refreshed_at).toLocaleTimeString()
    : "--:--:--";
  const refreshError = summary?.refresh_error ?? null;

  if (loading) {
    return (
      <div className="page resources-shell resources-shell--centered">
        <p className="resources-empty-text">加载资源中...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page resources-shell resources-shell--centered">
        <div className="resources-error-card">
          <h2>资源加载失败</h2>
          <p>{error}</p>
          <button type="button" className="resources-action-button" onClick={() => void retryLoad()}>
            重试
          </button>
        </div>
      </div>
    );
  }

  if (!selected) {
    return (
      <div className="page resources-shell resources-shell--centered">
        <p className="resources-empty-text">暂无已配置的提供商</p>
      </div>
    );
  }

  return (
    <div className="page resources-shell">
      <header className="resources-hero">
        <div className="resources-summary-strip">
          <div className="resources-summary-pill">
            <span className="resources-summary-dot resources-summary-dot--ok" />
            {summary?.active_providers ?? 0} 活跃 provider
          </div>
          <div className="resources-summary-pill">{leaseGroupCount} 沙盒</div>
          <div className="resources-summary-pill">{runningSessionCount} 运行中</div>
          {pausedSessionCount > 0 && <div className="resources-summary-pill">{pausedSessionCount} 已暂停</div>}
          {stoppedSessionCount > 0 && <div className="resources-summary-pill">{stoppedSessionCount} 已结束</div>}
          {providerOrphans.length > 0 && <div className="resources-summary-pill">{providerOrphans.length} 未绑定运行时</div>}
          <div className="resources-summary-pill">
            <span
              className={cx(
                "resources-summary-dot",
                summary?.refresh_status === "error" ? "resources-summary-dot--warn" : "resources-summary-dot--ok",
              )}
            />
            刷新 {refreshedAt}
          </div>
          <button
            type="button"
            className="resources-refresh-button"
            disabled={refreshing}
            onClick={() => void refreshNow()}
          >
            {refreshing ? "刷新中..." : "刷新"}
          </button>
        </div>
        {refreshError && <p className="resources-refresh-error">刷新失败: {refreshError}</p>}
      </header>

      <div className="resources-provider-grid">
        {providers.map((provider) => (
          <ProviderCard
            key={provider.id}
            provider={provider}
            selected={provider.id === selectedId}
            orphanCount={providerOrphans.filter((session) => session.provider === provider.id).length}
            onSelect={() => setSelectedId(provider.id)}
          />
        ))}
      </div>

      <ProviderDetail
        provider={selected}
        providerOrphans={selectedProviderOrphans}
        providerOrphansLoading={providerOrphansLoading}
        providerOrphansError={providerOrphansError}
        providerCleanupPendingId={providerCleanupPendingId}
        providerCleanupMessage={providerCleanupMessage}
        onCleanupProviderOrphan={cleanupProviderOrphan}
      />
    </div>
  );
}

function ProviderCard({
  provider,
  selected,
  orphanCount,
  onSelect,
}: {
  provider: ProviderInfo;
  selected: boolean;
  orphanCount: number;
  onSelect: () => void;
}) {
  const runningCount = countSessions(provider.sessions, "running");
  const pausedCount = countSessions(provider.sessions, "paused");
  const stoppedCount = countSessions(provider.sessions, "stopped");
  const runtimeUnboundRunningCount = countRuntimeUnboundRunning(provider);
  const detachedResidueCount = countDetachedResidue(provider.sessions);
  const unavailableHint =
    provider.unavailableReason ||
    (provider.type === "container" ? "需要容器运行时" : "当前进程未安装对应 SDK");
  const sessionSummary = [
    `${runningCount} 运行中`,
    pausedCount > 0 ? `${pausedCount} 已暂停` : null,
    stoppedCount > 0 ? `${stoppedCount} 已结束` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const sessionDots = [...provider.sessions]
    .sort((left, right) => (SESSION_STATUS_ORDER[left.status] ?? 4) - (SESSION_STATUS_ORDER[right.status] ?? 4))
    .slice(0, 5);

  return (
    <button
      type="button"
      className={cx(
        "provider-card",
        selected && "provider-card--selected",
        provider.status === "unavailable" && "provider-card--unavailable",
      )}
      onClick={onSelect}
    >
      <div className="provider-card__header">
        <div className="provider-card__title">
          <span className={`provider-status-dot provider-status-dot--${provider.status}`} />
          <span>{provider.name}</span>
        </div>
        <span className="provider-card__kind">
          <span className="provider-card__type-glyph" aria-hidden="true">
            {PROVIDER_TYPE_GLYPH[provider.type]}
          </span>
          {PROVIDER_TYPE_LABEL[provider.type]}
        </span>
      </div>

      {provider.status === "unavailable" ? (
        // @@@unavailable-card-state - monitor cards must say when a provider is unavailable;
        // showing a neutral `-- CPU` card hides the actionable state.
        <div className="provider-card__unavailable">
          <div className="provider-card__unavailable-label">未就绪</div>
          <div className="provider-card__unavailable-reason">{unavailableHint}</div>
        </div>
      ) : (
        <div className="provider-card__metric-row">
          <div className="provider-card__running-stat">
            <div className="provider-card__running-value">{formatNumber(runningCount)}</div>
            <div className="provider-card__running-copy">
              <div className="provider-card__running-label">运行中沙盒</div>
              <div className="provider-card__running-note">具体指标见下方沙盒</div>
            </div>
          </div>
        </div>
      )}

      <div className="provider-card__footer">
        {provider.sessions.length > 0 && (
          <div className="provider-card__activity">
            <div className="provider-card__session-dots" aria-hidden="true">
              {sessionDots.map((session) => (
                <span
                  key={session.id}
                  className={cx("provider-card__session-dot", `provider-card__session-dot--${session.status}`)}
                />
              ))}
            </div>
            <span>{sessionSummary}</span>
          </div>
        )}
        {runtimeUnboundRunningCount > 0 && <span>{runtimeUnboundRunningCount} 未连上沙盒</span>}
        {detachedResidueCount > 0 && <span>{detachedResidueCount} 历史残留</span>}
        {orphanCount > 0 && <span>{orphanCount} 未绑定运行时</span>}
      </div>

      <CapabilityStrip capabilities={provider.capabilities} />
    </button>
  );
}

function ProviderDetail({
  provider,
  providerOrphans,
  providerOrphansLoading,
  providerOrphansError,
  providerCleanupPendingId,
  providerCleanupMessage,
  onCleanupProviderOrphan,
}: {
  provider: ProviderInfo;
  providerOrphans: ProviderOrphanSession[];
  providerOrphansLoading: boolean;
  providerOrphansError: string | null;
  providerCleanupPendingId: string | null;
  providerCleanupMessage: string | null;
  onCleanupProviderOrphan: (session: ProviderOrphanSession) => Promise<void>;
}) {
  const [selectedGroup, setSelectedGroup] = React.useState<LeaseGroup | null>(null);
  const [statusFilter, setStatusFilter] = React.useState<LeaseGroup["status"] | "all">("all");
  const groups = React.useMemo(() => groupByLease(provider.sessions), [provider.sessions]);
  const filteredGroups = React.useMemo(
    () => (statusFilter === "all" ? groups : groups.filter((group) => group.status === statusFilter)),
    [groups, statusFilter],
  );
  const groupCounts = React.useMemo(
    () =>
      groups.reduce(
        (counts, group) => {
          counts[group.status] += 1;
          return counts;
        },
        {
          running: 0,
          paused: 0,
          stopped: 0,
          destroying: 0,
        } satisfies Record<LeaseGroup["status"], number>,
      ),
    [groups],
  );
  const runningCount = countSessions(provider.sessions, "running");
  const detachedResidueCount = countDetachedResidue(provider.sessions);
  const runtimeUnboundRunningCount = countRuntimeUnboundRunning(provider);
  const pausedCount = countSessions(provider.sessions, "paused");
  const stoppedCount = countSessions(provider.sessions, "stopped");
  const isLocal = provider.type === "local";
  const showUnavailableBanner = provider.status === "unavailable";
  const hardUnavailable = provider.status === "unavailable" && provider.sessions.length === 0;

  React.useEffect(() => {
    setStatusFilter(defaultProviderStatusFilter(groups));
  }, [groups, provider.id]);

  return (
    <>
      <section className="provider-detail-card">
        <div className="provider-detail__header">
          <div>
            <div className="provider-detail__title-row">
              <h2>{provider.name}</h2>
              <span className={`provider-detail__status provider-detail__status--${provider.status}`}>
                {STATUS_LABEL[provider.status]}
              </span>
            </div>
            <p className="provider-detail__description">
              {provider.description}
              {provider.vendor ? ` · ${provider.vendor}` : ""}
            </p>
          </div>
          <div className="provider-detail__meta">
            <span>{PROVIDER_TYPE_LABEL[provider.type]}</span>
            <Link to={`/providers/${provider.id}`} aria-label={`${provider.name} detail`}>
              详情
            </Link>
            {provider.consoleUrl && (
              <a href={provider.consoleUrl} target="_blank" rel="noreferrer">
                控制台
              </a>
            )}
          </div>
        </div>

        {hardUnavailable ? (
          <div className="provider-unavailable-panel">
            <h3>{provider.unavailableReason || "Provider unavailable"}</h3>
            <p>当前进程里这个 provider 没有起来，所以这里只保留卡片，不假装它能正常使用。</p>
          </div>
        ) : (
          <>
            {showUnavailableBanner && (
              // @@@unavailable-with-sessions - monitor state differs from the app resource tab:
              // an unavailable provider can still carry historical/live lease rows, so keep the detail
              // surface inspectable instead of hard-disabling the whole card.
              <div className="provider-warning-banner">
                {provider.unavailableReason || "Provider unavailable"}。但当前仍有 {provider.sessions.length} 条关联 session，可继续检查。
              </div>
            )}

            <div className="provider-detail__overview">
              <div className="provider-inline-metrics">
                <InlineMetric label="运行中" value={String(runningCount)} />
                {pausedCount > 0 && <InlineMetric label="已暂停" value={String(pausedCount)} />}
                {stoppedCount > 0 && <InlineMetric label="已结束" value={String(stoppedCount)} />}
                {runtimeUnboundRunningCount > 0 && !isLocal && (
                  <InlineMetric label="未连上沙盒" value={String(runtimeUnboundRunningCount)} />
                )}
                {detachedResidueCount > 0 && <InlineMetric label="历史残留" value={String(detachedResidueCount)} />}
              </div>
            </div>

            <ProviderOrphanSection
              sessions={providerOrphans}
              loading={providerOrphansLoading}
              error={providerOrphansError}
              cleanupPendingId={providerCleanupPendingId}
              cleanupMessage={providerCleanupMessage}
              onCleanup={onCleanupProviderOrphan}
            />

            <div className="provider-section">
              <div className="provider-section__header">
                <h3>沙盒</h3>
                <span>{filteredGroups.length} / {groups.length} 组</span>
              </div>
              {groups.length > 0 && (
                <div className="provider-filter-row" role="group" aria-label="Sandbox status filters">
                  <button
                    type="button"
                    className={cx("provider-filter-chip", statusFilter === "all" && "provider-filter-chip--active")}
                    onClick={() => setStatusFilter("all")}
                  >
                    全部 {groups.length}
                  </button>
                  {SANDBOX_FILTER_STATUSES.filter((status) => groupCounts[status] > 0).map((status) => (
                    <button
                      key={status}
                      type="button"
                      className={cx(
                        "provider-filter-chip",
                        statusFilter === status && "provider-filter-chip--active",
                      )}
                      onClick={() => setStatusFilter(status)}
                    >
                      {STATUS_LABEL[status]} {groupCounts[status]}
                    </button>
                  ))}
                </div>
              )}
              {groups.length === 0 ? (
                <p className="provider-empty-state">暂无沙盒</p>
              ) : filteredGroups.length === 0 ? (
                <p className="provider-empty-state">当前筛选下暂无沙盒</p>
              ) : (
                <div className="sandbox-grid">
                  {filteredGroups.map((group) => (
                    <SandboxCard
                      key={group.leaseId || group.sessions.map((session) => session.id).join("|")}
                      group={group}
                      providerType={provider.type}
                      onOpen={() => setSelectedGroup(group)}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </section>

      <SandboxInspector
        group={selectedGroup}
        providerType={provider.type}
        onClose={() => setSelectedGroup(null)}
      />
    </>
  );
}

function ProviderOrphanSection({
  sessions,
  loading,
  error,
  cleanupPendingId,
  cleanupMessage,
  onCleanup,
}: {
  sessions: ProviderOrphanSession[];
  loading: boolean;
  error: string | null;
  cleanupPendingId: string | null;
  cleanupMessage: string | null;
  onCleanup: (session: ProviderOrphanSession) => Promise<void>;
}) {
  if (!loading && !error && sessions.length === 0) {
    return null;
  }

  return (
    <div className="provider-section provider-orphan-panel">
      <div className="provider-section__header">
        <h3>未绑定运行时</h3>
        <span>{sessions.length} 个</span>
      </div>
      <p className="provider-orphan-note">
        这些运行时存在于 provider，但没有 lease/thread 绑定。暂停态可以直接走 Monitor 清理；运行中或未知状态先保留。
      </p>
      {loading && <p className="provider-empty-state">正在检查 provider 运行时...</p>}
      {error && <p className="provider-orphan-error">{error}</p>}
      {cleanupMessage && <p className="provider-orphan-message">{cleanupMessage}</p>}
      {sessions.length > 0 && (
        <div className="provider-orphan-list">
          {sessions.map((session) => {
            const pendingId = `${session.provider}:${session.session_id}`;
            const cleanupAllowed = session.status === "paused";
            return (
              <div key={pendingId} className="provider-orphan-row">
                <div className="provider-orphan-row__main">
                  <span className={`provider-status-dot provider-status-dot--${session.status}`} />
                  <div>
                    <div className="provider-orphan-row__id">{session.session_id}</div>
                    <div className="provider-orphan-row__meta">{session.status}</div>
                  </div>
                </div>
                <button
                  type="button"
                  className="provider-orphan-cleanup-button"
                  disabled={!cleanupAllowed || cleanupPendingId === pendingId}
                  title={cleanupAllowed ? "清理暂停态未绑定运行时" : "运行中或未知状态需要先确认归属"}
                  onClick={() => void onCleanup(session)}
                >
                  {cleanupPendingId === pendingId ? "清理中..." : cleanupAllowed ? "清理" : "先保留"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CapabilityStrip({ capabilities }: { capabilities: ProviderCapabilities }) {
  const keys = Object.keys(capabilities) as Array<keyof ProviderCapabilities>;
  const enabledCount = keys.filter((key) => capabilities[key]).length;

  return (
    <div className="provider-card__capability-strip">
      {keys.map((key) => {
        const enabled = capabilities[key];
        const Icon = CAPABILITY_ICON_MAP[key];
        return (
          <span
            key={key}
            role="img"
            aria-label={`${key} ${enabled ? "enabled" : "unavailable"}`}
            title={CAPABILITY_LABELS[key]}
            className={cx(
              "provider-capability-icon",
              enabled ? "provider-capability-icon--enabled" : "provider-capability-icon--disabled",
            )}
          >
            <Icon className="provider-capability-svg" aria-hidden="true" />
          </span>
        );
      })}
      <span className="provider-capability-count">
        {enabledCount}/{keys.length}
      </span>
    </div>
  );
}

function InlineMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="inline-metric">
      <span className="inline-metric__label">{label}</span>
      <span className="inline-metric__value">{value}</span>
    </div>
  );
}

function SandboxCard({
  group,
  providerType,
  onOpen,
}: {
  group: LeaseGroup;
  providerType: ProviderInfo["type"];
  onOpen: () => void;
}) {
  const duration = formatStartedAtDuration(group.startedAt);
  const names = group.sessions.map((session) => session.agentName || "未绑定").join(", ");
  const metrics = group.metrics;
  const hasMetrics =
    metrics != null &&
    (metrics.cpu != null ||
      metrics.memory != null ||
      metrics.memoryLimit != null ||
      metrics.disk != null ||
      metrics.diskLimit != null);
  const showRuntimeBindingWarning =
    providerType !== "local" &&
    group.status === "running" &&
    Boolean(group.leaseId) &&
    !group.sessions.some((session) => Boolean(session.runtimeSessionId));
  const showQuotaOnlyDiskState =
    metrics != null &&
    metrics.disk == null &&
    metrics.diskLimit != null &&
    Boolean(metrics.diskNote || metrics.probeError);
  const showDetachedResidueState =
    group.status === "stopped" &&
    !group.sessions.some((session) => Boolean(session.runtimeSessionId)) &&
    metrics == null;
  const showMissingMetricsState =
    group.status === "running" &&
    !showRuntimeBindingWarning &&
    !showQuotaOnlyDiskState &&
    !showDetachedResidueState &&
    (metrics == null || (metrics.cpu == null && metrics.memory == null && metrics.disk == null));

  return (
    <button type="button" className={`sandbox-card sandbox-card--${group.status}`} onClick={onOpen}>
      <div className="sandbox-card__top">
        <div className="sandbox-card__status">
          <span className={`provider-status-dot provider-status-dot--${group.status}`} />
          {STATUS_LABEL[group.status]}
        </div>
        <span className="sandbox-card__duration">{duration}</span>
      </div>
      <div className="sandbox-card__body">
        <div className="sandbox-card__agent-row">
          <div className="sandbox-card__avatar-stack">
            {group.sessions.slice(0, 3).map((session) => (
              <MonitorAvatar
                key={session.id}
                name={session.agentName || "未绑定"}
                avatarUrl={session.avatarUrl}
              />
            ))}
            {group.sessions.length > 3 && <MonitorAvatar name="" count={group.sessions.length - 3} />}
          </div>
          <div className="sandbox-card__names">{names}</div>
        </div>
        {showRuntimeBindingWarning && (
          // @@@running-card-without-runtime - a persisted lease row can still say `running`
          // after the live runtime session disappears; the card has to surface that drift
          // before opening a guaranteed-failing file browser.
          <div className="sandbox-card__warning">未连上运行时</div>
        )}
        {showQuotaOnlyDiskState && <div className="sandbox-card__warning">仅有磁盘配额</div>}
        {showDetachedResidueState && <div className="sandbox-card__warning">历史残留</div>}
        {showMissingMetricsState && <div className="sandbox-card__warning">等待运行中的沙盒上报指标</div>}
        <div className="sandbox-card__thread-list">
          {group.sessions.slice(0, 2).map((session) => (
            <div key={session.id} className="sandbox-card__thread">
              {session.threadId}
            </div>
          ))}
        </div>
      </div>
      {hasMetrics && (
        <div className="sandbox-card__metrics">
          <span>CPU {formatSessionMetricRange(metrics?.cpu, null, "%")}</span>
          <span>RAM {formatSessionMetricRange(metrics?.memory, metrics?.memoryLimit, "GB")}</span>
          <span>Disk {formatSessionMetricRange(metrics?.disk, metrics?.diskLimit, "GB")}</span>
        </div>
      )}
      <div className="sandbox-card__lease">{group.leaseId || "local"}</div>
    </button>
  );
}

function SandboxInspector({
  group,
  providerType,
  onClose,
}: {
  group: LeaseGroup | null;
  providerType: ProviderInfo["type"];
  onClose: () => void;
}) {
  React.useEffect(() => {
    if (!group) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [group, onClose]);

  if (!group) return null;
  const browserUnavailableReason =
    group.status === "paused"
      ? "沙盒已暂停，恢复运行后才能浏览文件。"
      : providerType !== "local" && group.leaseId && !group.sessions.some((session) => Boolean(session.runtimeSessionId))
        ? "当前 lease 没有 active runtime session，无法浏览文件。"
        : null;

  return (
    <div className="sandbox-modal-backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="sandbox-modal" onClick={(event) => event.stopPropagation()}>
        <div className="sandbox-modal__header">
          <div>
            <p className="sandbox-modal__eyebrow">
              {STATUS_LABEL[group.status]} · {formatStartedAtDuration(group.startedAt)}
            </p>
            <h3>{group.leaseId || "local"}</h3>
          </div>
          <button type="button" className="sandbox-modal__close" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="sandbox-modal__section">
          <h4>Agent</h4>
          <div className="sandbox-session-list">
            {group.sessions.map((session) => (
              <div key={session.id} className="sandbox-session-row">
                <div className="sandbox-session-row__identity">
                  <MonitorAvatar
                    name={session.agentName || "未绑定"}
                    avatarUrl={session.avatarUrl}
                    size="lg"
                  />
                  <div>
                    <div className="sandbox-session-row__name">{session.agentName || "未绑定"}</div>
                    <div className="sandbox-session-row__meta">
                      <Link className="sandbox-link" to={`/threads/${session.threadId}`}>
                        {session.threadId}
                      </Link>
                    </div>
                    {session.runtimeSessionId && (
                      <div className="sandbox-session-row__meta">
                        runtime{" "}
                        <Link className="sandbox-link" to={`/runtimes/${session.runtimeSessionId}`}>
                          {session.runtimeSessionId}
                        </Link>
                      </div>
                    )}
                  </div>
                </div>
                <div className="sandbox-session-row__status">
                  <span className={`provider-status-dot provider-status-dot--${session.status}`} />
                  <span>{STATUS_LABEL[session.status]}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {group.metrics && (
          <div className="sandbox-modal__section">
            <h4>实时指标</h4>
            <div className="sandbox-metric-grid">
              <MetricBlock label="CPU" value={formatMetric(group.metrics.cpu, "%")} />
              <MetricBlock
                label="RAM"
                value={group.metrics.memory != null ? formatMetric(group.metrics.memory, "GB") : "--"}
                sub={group.metrics.memoryLimit != null ? formatMetric(group.metrics.memoryLimit, "GB") : undefined}
                note={group.metrics.memoryNote || undefined}
              />
              <MetricBlock
                label="Disk"
                value={group.metrics.disk != null ? formatMetric(group.metrics.disk, "GB") : "--"}
                sub={group.metrics.diskLimit != null ? formatMetric(group.metrics.diskLimit, "GB") : undefined}
                note={group.metrics.diskNote || group.metrics.probeError || undefined}
              />
            </div>
          </div>
        )}

        <div className="sandbox-modal__section sandbox-modal__section--fill">
          <div className="sandbox-modal__section-header">
            <h4>工作区文件</h4>
            {group.leaseId ? (
              <Link className="sandbox-link" to={`/leases/${group.leaseId}`}>
                {group.leaseId}
              </Link>
            ) : null}
          </div>
          <MonitorFileBrowser
            leaseId={group.leaseId}
            providerType={providerType}
            disabled={group.status === "stopped" || group.status === "destroying"}
            unavailableReason={browserUnavailableReason}
          />
        </div>
      </div>
    </div>
  );
}

function MetricBlock({
  label,
  value,
  sub,
  note,
}: {
  label: string;
  value: string;
  sub?: string;
  note?: string;
}) {
  return (
    <div className="sandbox-metric-block">
      <div className="sandbox-metric-block__label">{label}</div>
      <div className="sandbox-metric-block__value">
        {value}
        {sub ? <span className="sandbox-metric-block__sub"> / {sub}</span> : null}
      </div>
      {note ? <div className="sandbox-metric-block__note">{note}</div> : null}
    </div>
  );
}

function MonitorFileBrowser({
  leaseId,
  providerType,
  disabled,
  unavailableReason,
}: {
  leaseId: string;
  providerType: ProviderInfo["type"];
  disabled: boolean;
  unavailableReason?: string | null;
}) {
  const isLocal = providerType === "local" || !leaseId;
  const defaultPath = isLocal ? "~" : "/";
  const [currentPath, setCurrentPath] = React.useState(defaultPath);
  const [parentPath, setParentPath] = React.useState<string | null>(null);
  const [items, setItems] = React.useState<BrowseItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedFile, setSelectedFile] = React.useState<string | null>(null);
  const [fileContent, setFileContent] = React.useState<string | null>(null);
  const [fileError, setFileError] = React.useState<string | null>(null);
  const [fileLoading, setFileLoading] = React.useState(false);

  const loadPath = React.useCallback(
    async (path: string) => {
      setLoading(true);
      setError(null);
      try {
        // @@@local-monitor-browse - local resource sessions are host-bound, not active-instance-bound.
        // Reuse the same settings browse/read endpoints as the app resource surface.
        const data = isLocal
          ? await fetchJsonOrThrow<{
                current_path?: string;
                parent_path?: string | null;
                items?: BrowseItem[];
              }>(`/api/settings/browse?path=${encodeURIComponent(path)}&include_files=true`)
          : await browseMonitorSandbox(leaseId, path);
        setCurrentPath(data.current_path ?? path);
        setParentPath(data.parent_path ?? null);
        setItems(data.items ?? []);
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "浏览失败");
      } finally {
        setLoading(false);
      }
    },
    [isLocal, leaseId],
  );

  React.useEffect(() => {
    if (disabled || unavailableReason) return;
    void loadPath(defaultPath);
    setSelectedFile(null);
    setFileContent(null);
    setFileError(null);
  }, [defaultPath, disabled, loadPath, unavailableReason]);

  const loadFile = React.useCallback(
    async (path: string) => {
      setFileContent(null);
      setFileError(null);
      setFileLoading(true);
      try {
        const data = isLocal
          ? await fetchJsonOrThrow<{ content: string; truncated: boolean }>(
              `/api/settings/read?path=${encodeURIComponent(path)}`,
            )
          : await readMonitorSandboxFile(leaseId, path);
        setFileContent(data.content);
        if (data.truncated) {
          setFileError("内容已截断至 100 KB");
        }
      } catch (exc) {
        setFileError(exc instanceof Error ? exc.message : "读取失败");
      } finally {
        setFileLoading(false);
      }
    },
    [isLocal, leaseId],
  );

  const openFile = React.useCallback(
    async (path: string) => {
      if (selectedFile === path) {
        setSelectedFile(null);
        setFileContent(null);
        setFileError(null);
        return;
      }
      setSelectedFile(path);
      await loadFile(path);
    },
    [selectedFile, loadFile],
  );

  if (unavailableReason) {
    return <p className="file-browser__empty">{unavailableReason}</p>;
  }

  if (disabled) {
    return <p className="file-browser__empty">沙盒已停止，无法浏览文件。</p>;
  }

  return (
    <div className="file-browser">
      <div className="file-browser__column">
        <div className="file-browser__pathbar">
          <button type="button" onClick={() => void loadPath(defaultPath)}>
            Root
          </button>
          <span>{providerType}</span>
          <strong>{currentPath}</strong>
        </div>
        <div className="file-browser__list">
          {parentPath && (
            <button type="button" className="file-browser__item" onClick={() => void loadPath(parentPath)}>
              .. (上一级)
            </button>
          )}
          {loading && <p className="file-browser__empty">加载中...</p>}
          {error && (
            <div className="file-browser__error-stack">
              <p className="file-browser__error">{error}</p>
              <button type="button" className="file-browser__retry" onClick={() => void loadPath(currentPath)}>
                重试
              </button>
            </div>
          )}
          {!loading && !error && items.length === 0 && <p className="file-browser__empty">此目录为空</p>}
          {!loading &&
            !error &&
            items.map((item) => (
              <button
                key={item.path}
                type="button"
                className={cx(
                  "file-browser__item",
                  !item.is_dir && selectedFile === item.path && "file-browser__item--selected",
                )}
                onClick={() => (item.is_dir ? void loadPath(item.path) : void openFile(item.path))}
              >
                <span>{item.is_dir ? "DIR" : "FILE"}</span>
                <span>{item.name}</span>
              </button>
            ))}
        </div>
      </div>
      <div className="file-browser__column file-browser__column--content">
        {selectedFile ? (
          <>
            <div className="file-browser__pathbar">
              <strong>{selectedFile}</strong>
            </div>
            <div className="file-browser__content">
              {fileLoading && <p className="file-browser__empty">读取中...</p>}
              {!fileLoading && fileError && !fileContent && (
                <div className="file-browser__error-stack">
                  <p className="file-browser__error">{fileError}</p>
                  <button
                    type="button"
                    className="file-browser__retry"
                    onClick={() => {
                      if (selectedFile) void loadFile(selectedFile);
                    }}
                  >
                    重试
                  </button>
                </div>
              )}
              {fileContent != null && <pre>{fileContent}</pre>}
              {fileContent != null && fileError && <p className="file-browser__note">{fileError}</p>}
            </div>
          </>
        ) : (
          <div className="file-browser__content file-browser__content--empty">选择文件查看内容</div>
        )}
      </div>
    </div>
  );
}
