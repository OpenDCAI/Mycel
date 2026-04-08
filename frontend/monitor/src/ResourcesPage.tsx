import React from "react";
import { Link } from "react-router-dom";

import {
  browseMonitorSandbox,
  fetchMonitorResources,
  readMonitorSandboxFile,
  refreshMonitorResources,
} from "./resources/api";
import type {
  BrowseItem,
  ProviderCapabilities,
  ProviderInfo,
  ResourceOverviewResponse,
  ResourceSession,
  SessionMetrics,
  UsageMetric,
} from "./resources/types";

const PROVIDER_TYPE_LABEL = {
  local: "本地",
  cloud: "云端",
  container: "容器",
} as const;

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

interface LeaseGroup {
  leaseId: string;
  status: ResourceSession["status"];
  sessions: ResourceSession[];
  startedAt: string;
  metrics: SessionMetrics | null;
}

function formatNumber(value: number | null | undefined, nullText: string = "--"): string {
  if (value == null) {
    return nullText;
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

function formatMetricRange(metric: UsageMetric): string {
  if (metric.used == null && metric.limit == null) {
    return "--";
  }
  if (metric.used != null && metric.limit != null) {
    return `${formatMetric(metric.used, metric.unit)} / ${formatMetric(metric.limit, metric.unit)}`;
  }
  if (metric.used != null) {
    return formatMetric(metric.used, metric.unit);
  }
  return `limit ${formatMetric(metric.limit, metric.unit)}`;
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

function capabilityTags(capabilities: ProviderCapabilities): string[] {
  const labels: Array<[keyof ProviderCapabilities, string]> = [
    ["filesystem", "FS"],
    ["terminal", "TERM"],
    ["metrics", "METRIC"],
    ["web", "WEB"],
    ["screenshot", "SHOT"],
    ["mount", "MOUNT"],
  ];
  return labels.filter(([key]) => capabilities[key]).map(([, label]) => label);
}

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

export default function ResourcesPage() {
  const [providers, setProviders] = React.useState<ProviderInfo[]>([]);
  const [selectedId, setSelectedId] = React.useState("");
  const [summary, setSummary] = React.useState<ResourceOverviewResponse["summary"] | null>(null);
  const [triage, setTriage] = React.useState<ResourceOverviewResponse["triage"] | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const applyPayload = React.useCallback((payload: ResourceOverviewResponse) => {
    setProviders(payload.providers);
    setSummary(payload.summary);
    setTriage(payload.triage ?? null);
    setSelectedId((previous) => {
      if (payload.providers.some((provider) => provider.id === previous)) {
        return previous;
      }
      return payload.providers[0]?.id ?? "";
    });
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
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "资源加载失败");
    } finally {
      setRefreshing(false);
    }
  }, [applyPayload]);

  const refreshNow = React.useCallback(async () => {
    setRefreshing(true);
    try {
      const payload = await refreshMonitorResources();
      applyPayload(payload);
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
  }, [applyPayload, providers.length]);

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
    return () => {
      cancelled = true;
    };
  }, [applyPayload]);

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      void loadSnapshot();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [loadSnapshot]);

  const selected = providers.find((provider) => provider.id === selectedId) ?? null;
  const runningSessionCount = providers.reduce(
    (total, provider) => total + provider.sessions.filter((session) => session.status === "running").length,
    0,
  );
  const runtimeUnboundUsageCount = providers.reduce(
    (total, provider) =>
      total +
      provider.sessions.filter((session) => {
        const metrics = session.metrics;
        return (
          session.status === "running" &&
          provider.type !== "local" &&
          !session.runtimeSessionId &&
          metrics != null &&
          (metrics.cpu != null || metrics.memory != null || metrics.disk != null)
        );
      }).length,
    0,
  );
  const runtimeUnboundRunningCount = providers.reduce(
    (total, provider) =>
      total +
      provider.sessions.filter(
        (session) => provider.type !== "local" && session.status === "running" && !session.runtimeSessionId,
      ).length,
    0,
  );
  const liveUsageRunningCount = providers.reduce(
    (total, provider) =>
      total +
      provider.sessions.filter((session) => {
        const metrics = session.metrics;
        return (
          session.status === "running" &&
          metrics != null &&
          (metrics.cpu != null || metrics.memory != null || metrics.disk != null)
        );
      }).length,
    0,
  );
  const missingLiveTelemetryRunningCount = runningSessionCount - liveUsageRunningCount;
  const readyWithoutLiveTelemetryCount = providers.filter(
    (provider) =>
      provider.type !== "local" &&
      provider.status === "ready" &&
      provider.sessions.length === 0 &&
      provider.telemetry.cpu.freshness === "stale" &&
      provider.telemetry.memory.freshness === "stale" &&
      provider.telemetry.disk.freshness === "stale",
  ).length;
  const quotaOnlyRunningCount = providers.reduce(
    (total, provider) =>
      total +
      provider.sessions.filter((session) => {
        const metrics = session.metrics;
        return (
          session.status === "running" &&
          metrics != null &&
          metrics.memory == null &&
          metrics.disk == null &&
          (metrics.memoryLimit != null || metrics.diskLimit != null) &&
          Boolean(metrics.memoryNote || metrics.diskNote || metrics.probeError)
        );
      }).length,
    0,
  );
  const detachedResidueCount = triage?.summary?.detached_residue ?? 0;
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
        <div>
          <p className="resources-eyebrow">Global Resource Surface</p>
          <h1>Resources</h1>
          <p className="resources-hero-copy">
            沿用旧资源页的卡片式布局，但直接接到 monitor 的全局资源面。这里看 provider 级概览，再下钻到 lease/sandbox。
          </p>
        </div>
        <div className="resources-summary-strip">
          <div className="resources-summary-pill">
            <span className="resources-summary-dot resources-summary-dot--ok" />
            {summary?.active_providers ?? 0} 活跃 provider
          </div>
          <div className="resources-summary-pill">{runningSessionCount} 运行会话</div>
          {liveUsageRunningCount > 0 && liveUsageRunningCount < runningSessionCount && (
            <div className="resources-summary-pill">{liveUsageRunningCount} 有用量</div>
          )}
          {runtimeUnboundUsageCount > 0 && (
            <div className="resources-summary-pill">{runtimeUnboundUsageCount} 无 runtime有用量</div>
          )}
          {missingLiveTelemetryRunningCount > 0 && (
            <div className="resources-summary-pill">{missingLiveTelemetryRunningCount} 无 live telemetry</div>
          )}
          {runtimeUnboundRunningCount > 0 && (
            <div className="resources-summary-pill">{runtimeUnboundRunningCount} 无 runtime</div>
          )}
          {readyWithoutLiveTelemetryCount > 0 && (
            <div className="resources-summary-pill">{readyWithoutLiveTelemetryCount} 遥测未知</div>
          )}
          {quotaOnlyRunningCount > 0 && (
            <div className="resources-summary-pill">{quotaOnlyRunningCount} 仅配额</div>
          )}
          {detachedResidueCount > 0 && (
            <div className="resources-summary-pill">{detachedResidueCount} Detached Residue</div>
          )}
          <div className="resources-summary-pill">
            <span
              className={[
                "resources-summary-dot",
                summary?.refresh_status === "error" ? "resources-summary-dot--warn" : "resources-summary-dot--ok",
              ].join(" ")}
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
            onSelect={() => setSelectedId(provider.id)}
          />
        ))}
      </div>

      <ProviderDetail provider={selected} />
    </div>
  );
}

function ProviderCard({
  provider,
  selected,
  onSelect,
}: {
  provider: ProviderInfo;
  selected: boolean;
  onSelect: () => void;
}) {
  const runningCount = provider.sessions.filter((session) => session.status === "running").length;
  const runtimeUnboundUsageCount = provider.sessions.filter((session) => {
    const metrics = session.metrics;
    return (
      session.status === "running" &&
      !session.runtimeSessionId &&
      metrics != null &&
      (metrics.cpu != null || metrics.memory != null || metrics.disk != null)
    );
  }).length;
  const runtimeUnboundRunningCount = provider.sessions.filter(
    (session) => provider.type !== "local" && session.status === "running" && !session.runtimeSessionId,
  ).length;
  const liveUsageRunningCount = provider.sessions.filter((session) => {
    const metrics = session.metrics;
    return (
      session.status === "running" &&
      metrics != null &&
      (metrics.cpu != null || metrics.memory != null || metrics.disk != null)
    );
  }).length;
  const runtimeBoundTelemetryGapCount = provider.sessions.filter((session) => {
    const metrics = session.metrics;
    const hasLiveUsage = metrics != null && (metrics.cpu != null || metrics.memory != null || metrics.disk != null);
    const isQuotaOnly =
      metrics != null &&
      metrics.memory == null &&
      metrics.disk == null &&
      (metrics.memoryLimit != null || metrics.diskLimit != null) &&
      Boolean(metrics.memoryNote || metrics.diskNote || metrics.probeError);
    return session.status === "running" && Boolean(session.runtimeSessionId) && !hasLiveUsage && !isQuotaOnly;
  }).length;
  const quotaOnlyRunningCount = provider.sessions.filter((session) => {
    const metrics = session.metrics;
    return (
      session.status === "running" &&
      metrics != null &&
      metrics.memory == null &&
      metrics.disk == null &&
      (metrics.memoryLimit != null || metrics.diskLimit != null) &&
      Boolean(metrics.memoryNote || metrics.diskNote || metrics.probeError)
    );
  }).length;
  const missingLiveTelemetryRunningCount = runningCount - liveUsageRunningCount;
  const pausedCount = provider.sessions.filter((session) => session.status === "paused").length;
  const stoppedCount = provider.sessions.filter((session) => session.status === "stopped").length;
  const capabilityList = capabilityTags(provider.capabilities);
  const showCpuMetric = provider.cardCpu.used != null || provider.cardCpu.limit != null;
  const showMemoryMetric = provider.telemetry.memory.used != null || provider.telemetry.memory.limit != null;
  const showDiskMetric = provider.telemetry.disk.used != null || provider.telemetry.disk.limit != null;
  const runningMetric = {
    ...provider.telemetry.running,
    used: runningCount,
  };
  const showSandboxLevelCpuTruth =
    provider.type !== "local" &&
    runningCount > 0 &&
    !showCpuMetric &&
    provider.cardCpu.error === "CPU usage is per-sandbox, not a provider-level quota.";
  const showTelemetryGapTruth =
    provider.type !== "local" &&
    provider.status === "ready" &&
    runningCount === 0 &&
    provider.telemetry.cpu.freshness === "stale" &&
    provider.telemetry.memory.freshness === "stale" &&
    provider.telemetry.disk.freshness === "stale";
  const unavailableHint =
    provider.unavailableReason ||
    (provider.type === "container" ? "需要容器运行时" : "当前进程未安装对应 SDK");

  return (
    <button
      type="button"
      className={[
        "provider-card",
        selected ? "provider-card--selected" : "",
        provider.status === "unavailable" ? "provider-card--unavailable" : "",
      ].join(" ")}
      onClick={onSelect}
    >
      <div className="provider-card__header">
        <div className="provider-card__title">
          <span className={`provider-status-dot provider-status-dot--${provider.status}`} />
          <span>{provider.name}</span>
        </div>
        <span className="provider-card__kind">{PROVIDER_TYPE_LABEL[provider.type]}</span>
      </div>

      {provider.status === "unavailable" ? (
        // @@@unavailable-card-truth - monitor cards must say when a provider is unavailable;
        // showing a neutral `-- CPU` card hides the real operator actionability.
        <div className="provider-card__unavailable">
          <div className="provider-card__unavailable-label">未就绪</div>
          <div className="provider-card__unavailable-reason">{unavailableHint}</div>
        </div>
      ) : (
        <div className="provider-card__metric-row">
          <MetricOrb label="运行数" metric={runningMetric} />
          {showCpuMetric && <MetricOrb label="CPU" metric={provider.cardCpu} />}
          {showMemoryMetric && <MetricOrb label="RAM" metric={provider.telemetry.memory} />}
          {showDiskMetric && <MetricOrb label="Disk" metric={provider.telemetry.disk} />}
        </div>
      )}

      <div className="provider-card__footer">
        <span>{runningCount} 占用中</span>
        {liveUsageRunningCount > 0 && liveUsageRunningCount < runningCount && <span>{liveUsageRunningCount} 有用量</span>}
        {missingLiveTelemetryRunningCount > 0 && <span>{missingLiveTelemetryRunningCount} 无 live telemetry</span>}
        {runtimeBoundTelemetryGapCount > 0 && <span>{runtimeBoundTelemetryGapCount} 有 runtime无遥测</span>}
        {runtimeUnboundUsageCount > 0 && <span>{runtimeUnboundUsageCount} 无 runtime有用量</span>}
        {quotaOnlyRunningCount > 0 && <span>{quotaOnlyRunningCount} 仅配额</span>}
        {runtimeUnboundRunningCount > 0 && <span>{runtimeUnboundRunningCount} 无 runtime</span>}
        {pausedCount > 0 && <span>{pausedCount} 暂停</span>}
        {stoppedCount > 0 && <span>{stoppedCount} 已结束</span>}
      </div>

      {showTelemetryGapTruth && (
        <div className="provider-card__truth">暂无 live telemetry</div>
      )}
      {showSandboxLevelCpuTruth && (
        <div className="provider-card__truth">CPU 沙盒级</div>
      )}

      {capabilityList.length > 0 && (
        <div className="provider-card__capabilities">
          {capabilityList.map((capability) => (
            <span key={capability} className="provider-capability-chip">
              {capability}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

function MetricOrb({ label, metric }: { label: string; metric: UsageMetric }) {
  const value =
    metric.used == null
      ? "--"
      : metric.unit === "%" || metric.unit === "GB"
        ? formatMetric(metric.used, metric.unit)
        : formatNumber(metric.used);

  return (
    <div className="metric-orb" title={metric.error || undefined}>
      <div className="metric-orb__value">{value}</div>
      <div className="metric-orb__label">{label}</div>
      {metric.limit != null && <div className="metric-orb__sub">{formatMetric(metric.limit, metric.unit)}</div>}
    </div>
  );
}

function ProviderDetail({ provider }: { provider: ProviderInfo }) {
  const [selectedGroup, setSelectedGroup] = React.useState<LeaseGroup | null>(null);
  const groups = React.useMemo(() => groupByLease(provider.sessions), [provider.sessions]);
  const runningCount = provider.sessions.filter((session) => session.status === "running").length;
  const detachedResidueCount = provider.sessions.filter(
    (session) => session.status === "stopped" && !session.runtimeSessionId && session.metrics == null,
  ).length;
  const runtimeUnboundUsageCount = provider.sessions.filter((session) => {
    const metrics = session.metrics;
    return (
      session.status === "running" &&
      !session.runtimeSessionId &&
      metrics != null &&
      (metrics.cpu != null || metrics.memory != null || metrics.disk != null)
    );
  }).length;
  const runtimeUnboundRunningCount = provider.sessions.filter(
    (session) => session.status === "running" && !session.runtimeSessionId,
  ).length;
  const quotaOnlyRunningCount = provider.sessions.filter((session) => {
    const metrics = session.metrics;
    return (
      session.status === "running" &&
      metrics != null &&
      metrics.memory == null &&
      metrics.disk == null &&
      (metrics.memoryLimit != null || metrics.diskLimit != null) &&
      Boolean(metrics.memoryNote || metrics.diskNote || metrics.probeError)
    );
  }).length;
  const liveUsageRunningCount = provider.sessions.filter((session) => {
    const metrics = session.metrics;
    return (
      session.status === "running" &&
      metrics != null &&
      (metrics.cpu != null || metrics.memory != null || metrics.disk != null)
    );
  }).length;
  const runtimeBoundTelemetryGapCount = provider.sessions.filter((session) => {
    const metrics = session.metrics;
    const hasLiveUsage = metrics != null && (metrics.cpu != null || metrics.memory != null || metrics.disk != null);
    const isQuotaOnly =
      metrics != null &&
      metrics.memory == null &&
      metrics.disk == null &&
      (metrics.memoryLimit != null || metrics.diskLimit != null) &&
      Boolean(metrics.memoryNote || metrics.diskNote || metrics.probeError);
    return session.status === "running" && Boolean(session.runtimeSessionId) && !hasLiveUsage && !isQuotaOnly;
  }).length;
  const missingLiveTelemetryRunningCount = runningCount - liveUsageRunningCount;
  const pausedCount = provider.sessions.filter((session) => session.status === "paused").length;
  const stoppedCount = provider.sessions.filter((session) => session.status === "stopped").length;
  const isLocal = provider.type === "local";
  const showUnavailableBanner = provider.status === "unavailable";
  const hardUnavailable = provider.status === "unavailable" && provider.sessions.length === 0;
  const showTelemetryGapBanner =
    !isLocal &&
    provider.status === "ready" &&
    runningCount === 0 &&
    provider.telemetry.cpu.freshness === "stale" &&
    provider.telemetry.memory.freshness === "stale" &&
    provider.telemetry.disk.freshness === "stale";

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
              // @@@unavailable-with-sessions - monitor truth differs from the old app resource tab:
              // an unavailable provider can still carry historical/live lease rows, so keep the detail
              // surface inspectable instead of hard-disabling the whole card.
              <div className="provider-warning-banner">
                {provider.unavailableReason || "Provider unavailable"}。但当前仍有 {provider.sessions.length} 条关联 session，可继续检查。
              </div>
            )}
            {showTelemetryGapBanner && (
              <div className="provider-warning-banner">
                当前 provider 暂无 live telemetry，CPU / RAM / Disk 仍是未知状态。
              </div>
            )}

            <div className="provider-detail__overview">
              {isLocal ? (
                <div className="provider-inline-metrics">
                  <InlineMetric label="运行中" value={String(runningCount)} />
                  {liveUsageRunningCount > 0 && liveUsageRunningCount < runningCount && (
                    <InlineMetric label="有用量" value={String(liveUsageRunningCount)} />
                  )}
                  {missingLiveTelemetryRunningCount > 0 && (
                    <InlineMetric label="无 live telemetry" value={String(missingLiveTelemetryRunningCount)} />
                  )}
                  {detachedResidueCount > 0 && <InlineMetric label="Detached Residue" value={String(detachedResidueCount)} />}
                  <InlineMetric label="CPU" value={formatMetricRange(provider.cardCpu)} />
                  <InlineMetric label="RAM" value={formatMetricRange(provider.telemetry.memory)} />
                  <InlineMetric label="Disk" value={formatMetricRange(provider.telemetry.disk)} />
                </div>
              ) : (
                <div className="provider-inline-metrics">
                  <InlineMetric label="运行中" value={String(runningCount)} />
                  {liveUsageRunningCount > 0 && liveUsageRunningCount < runningCount && (
                    <InlineMetric label="有用量" value={String(liveUsageRunningCount)} />
                  )}
                  {missingLiveTelemetryRunningCount > 0 && (
                    <InlineMetric label="无 live telemetry" value={String(missingLiveTelemetryRunningCount)} />
                  )}
                  {runtimeBoundTelemetryGapCount > 0 && (
                    <InlineMetric label="有 runtime无遥测" value={String(runtimeBoundTelemetryGapCount)} />
                  )}
                  {runtimeUnboundUsageCount > 0 && (
                    <InlineMetric label="无 runtime有用量" value={String(runtimeUnboundUsageCount)} />
                  )}
                  {runtimeUnboundRunningCount > 0 && <InlineMetric label="无 runtime" value={String(runtimeUnboundRunningCount)} />}
                  {quotaOnlyRunningCount > 0 && <InlineMetric label="仅配额" value={String(quotaOnlyRunningCount)} />}
                  <InlineMetric label="已暂停" value={String(pausedCount)} />
                  {detachedResidueCount > 0 && <InlineMetric label="Detached Residue" value={String(detachedResidueCount)} />}
                  <InlineMetric label="已结束" value={String(stoppedCount)} />
                </div>
              )}
            </div>

            <div className="provider-section">
              <div className="provider-section__header">
                <h3>Sandboxes</h3>
                <span>{groups.length} 组</span>
              </div>
              {groups.length === 0 ? (
                <p className="provider-empty-state">暂无沙盒</p>
              ) : (
                <div className="sandbox-grid">
                  {groups.map((group) => (
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
  const showQuotaOnlyDiskTruth =
    metrics != null &&
    metrics.disk == null &&
    metrics.diskLimit != null &&
    Boolean(metrics.diskNote || metrics.probeError);
  const showMissingLiveTelemetryTruth =
    group.status === "running" &&
    !showRuntimeBindingWarning &&
    !showQuotaOnlyDiskTruth &&
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
              <div key={session.id} className="sandbox-avatar" title={session.agentName || "未绑定"}>
                {session.avatarUrl ? <img src={session.avatarUrl} alt="" /> : initials(session.agentName || "未绑定")}
              </div>
            ))}
            {group.sessions.length > 3 && <div className="sandbox-avatar sandbox-avatar--count">+{group.sessions.length - 3}</div>}
          </div>
          <div className="sandbox-card__names">{names}</div>
        </div>
        {showRuntimeBindingWarning && (
          // @@@running-card-without-runtime - a persisted lease row can still say `running`
          // after the live runtime session disappears; the card has to surface that drift
          // before the operator drills into a guaranteed-failing file browser.
          <div className="sandbox-card__warning">无 active runtime</div>
        )}
        {showQuotaOnlyDiskTruth && <div className="sandbox-card__warning">Disk 仅配额</div>}
        {showMissingLiveTelemetryTruth && <div className="sandbox-card__warning">无 live telemetry</div>}
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
    providerType !== "local" && group.leaseId && !group.sessions.some((session) => Boolean(session.runtimeSessionId))
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
                  <div className="sandbox-avatar sandbox-avatar--lg" title={session.agentName || "未绑定"}>
                    {session.avatarUrl ? <img src={session.avatarUrl} alt="" /> : initials(session.agentName || "未绑定")}
                  </div>
                  <div>
                    <div className="sandbox-session-row__name">{session.agentName || "未绑定"}</div>
                    <Link className="sandbox-link" to={`/thread/${session.threadId}`}>
                      {session.threadId}
                    </Link>
                    {session.runtimeSessionId && (
                      <div className="sandbox-session-row__meta">runtime {session.runtimeSessionId}</div>
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
            <h4>指标</h4>
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
            <h4>文件</h4>
            {group.leaseId && (
              <Link className="sandbox-link" to={`/lease/${group.leaseId}`}>
                打开 lease
              </Link>
            )}
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
          ? await (async () => {
              const response = await fetch(`/api/settings/browse?path=${encodeURIComponent(path)}&include_files=true`);
              if (!response.ok) {
                const body = await response.text();
                throw new Error(`API ${response.status}: ${body || response.statusText}`);
              }
              return await response.json() as {
                current_path?: string;
                parent_path?: string | null;
                items?: BrowseItem[];
              };
            })()
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
    if (disabled) return;
    void loadPath(defaultPath);
    setSelectedFile(null);
    setFileContent(null);
    setFileError(null);
  }, [defaultPath, disabled, loadPath]);

  const loadFile = React.useCallback(
    async (path: string) => {
      setFileContent(null);
      setFileError(null);
      setFileLoading(true);
      try {
        const data = isLocal
          ? await (async () => {
              const response = await fetch(`/api/settings/read?path=${encodeURIComponent(path)}`);
              if (!response.ok) {
                const body = await response.text();
                throw new Error(`API ${response.status}: ${body || response.statusText}`);
              }
              return await response.json() as { content: string; truncated: boolean };
            })()
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
      if (!leaseId && !isLocal) return;
      if (selectedFile === path) {
        setSelectedFile(null);
        setFileContent(null);
        setFileError(null);
        return;
      }
      setSelectedFile(path);
      await loadFile(path);
    },
    [isLocal, leaseId, selectedFile, loadFile],
  );

  if (!leaseId && !isLocal) {
    return <p className="file-browser__empty">当前沙盒没有 lease id，无法浏览文件。</p>;
  }

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
                className={[
                  "file-browser__item",
                  !item.is_dir && selectedFile === item.path ? "file-browser__item--selected" : "",
                ].join(" ")}
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
