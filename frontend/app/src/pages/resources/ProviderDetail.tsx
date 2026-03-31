import { useState } from "react";
import { Monitor, Cloud, Container, Lock, Settings, ArrowRight, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import type { ProviderInfo, UsageMetric } from "./types";
import { groupByLease, useSessionCounts, type LeaseGroup } from "./session-list-utils";
import SandboxCard from "./SandboxCard";
import SandboxDetailSheet from "./SandboxDetailSheet";
import { formatNumber, formatLimit } from "./utils/format";

const typeIcon = {
  local: Monitor,
  cloud: Cloud,
  container: Container,
} as const;

const typeLabel = {
  local: "本地",
  cloud: "云端",
  container: "容器",
} as const;

const statusLabel = {
  active: "活跃",
  ready: "就绪",
  unavailable: "未就绪",
} as const;

interface ProviderDetailProps {
  provider: ProviderInfo;
}

export default function ProviderDetail({ provider }: ProviderDetailProps) {
  const { name, description, vendor, type, status, unavailableReason, telemetry, error } = provider;
  const TypeIcon = typeIcon[type];
  const { running: runningCount, paused: pausedCount, stopped: stoppedCount } = useSessionCounts(provider.sessions);
  const groups = groupByLease(provider.sessions);

  const [selectedGroup, setSelectedGroup] = useState<LeaseGroup | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  if (status === "unavailable") {
    return (
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/20">
          <div className="flex items-center gap-3">
            <TypeIcon className="w-4 h-4 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">{name}</h3>
              <p className="text-xs text-muted-foreground">{description}</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">{typeLabel[type]}</span>
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">{statusLabel[status]}</span>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center py-12 px-6">
          <Lock className="w-8 h-8 text-muted-foreground/40 mb-3" />
          <p className="text-sm text-muted-foreground mb-1">{unavailableReason}</p>
          {error?.message && <p className="text-xs text-muted-foreground/70 mb-2 font-mono">{error.message}</p>}
          <p className="text-xs text-muted-foreground mb-4">前往 设置 &gt; 沙箱 配置 {name} 环境</p>
          <Link
            to="/settings"
            className="inline-flex items-center gap-1.5 text-xs text-foreground hover:text-primary transition-colors duration-fast border border-border rounded-lg px-3 py-1.5"
          >
            <Settings className="w-3 h-3" />
            前往设置
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      </div>
    );
  }

  // @@@overview-semantic - local = host machine metrics (CPU/mem/disk are provider-level).
  // Non-local = session counts only; per-instance probe data is not a global provider quota.
  const isLocal = type === "local";

  return (
    <>
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        {/* Provider header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/20">
          <div className="flex items-center gap-3">
            <TypeIcon className="w-4 h-4 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">{name}</h3>
              <p className="text-xs text-muted-foreground">
                {description}
                {vendor && ` · ${vendor}`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {provider.consoleUrl && (
              <a
                href={provider.consoleUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-2xs text-muted-foreground hover:text-foreground"
              >
                控制台
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
            <span className="text-xs text-muted-foreground">{typeLabel[type]}</span>
            <span className="text-xs text-muted-foreground">·</span>
            <span className={`text-xs ${status === "active" ? "text-success" : "text-muted-foreground"}`}>
              {statusLabel[status]}
            </span>
          </div>
        </div>

        <div className="p-5">
          {/* Overview */}
          <div className="mb-1">
            <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">概览</span>
          </div>

          {isLocal ? (
            /* Local: compact strip with running count + host metrics inline */
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 mb-5 text-xs font-mono">
              <StatPill count={runningCount} label="运行中" dotClass="bg-success animate-pulse-slow" />
              <MetricPill label="CPU" metric={provider.cardCpu} />
              <MetricPill label="RAM" metric={telemetry.memory} />
              <MetricPill label="Disk" metric={telemetry.disk} />
            </div>
          ) : (
            /* Non-local: compact inline stat strip */
            <div className="flex items-center gap-5 mb-5 text-xs font-mono">
              <StatPill count={runningCount} label="运行中" dotClass="bg-success animate-pulse-slow" />
              {pausedCount > 0 && (
                <StatPill count={pausedCount} label="已暂停" dotClass="bg-warning/80" />
              )}
              <StatPill count={stoppedCount} label="已结束" dotClass="bg-muted-foreground/30" />
            </div>
          )}

          {telemetry.quota && (
            <div className="mb-5">
              <div className="mb-2">
                <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">配额</span>
              </div>
              <div className="rounded-lg bg-muted/15 border border-border/40 p-3">
                <StatBlock metric={telemetry.quota} label="quota" title="额度" compact />
              </div>
            </div>
          )}

          {/* Sandbox card grid */}
          <div>
            <div className="mb-3">
              <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">沙盒</span>
            </div>
            {groups.length === 0 ? (
              <p className="text-xs text-muted-foreground">暂无沙盒</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
                {groups.map((group) => (
                  <SandboxCard
                    key={group.leaseId || group.sessions.map((s) => s.id).join("|")}
                    group={group}
                    onClick={() => {
                      setSelectedGroup(group);
                      setSheetOpen(true);
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Detail sheet — rendered outside the card to avoid stacking context issues */}
      <SandboxDetailSheet
        group={selectedGroup}
        providerType={type}
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// StatPill (count-based, used in both local + non-local strips)
// ---------------------------------------------------------------------------

function StatPill({
  count,
  label,
  dotClass,
}: {
  count: number;
  label: string;
  dotClass: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`} />
      <span className="font-semibold text-foreground tabular-nums">{count}</span>
      <span className="text-muted-foreground">{label}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// MetricPill (value/limit, used in local strip)
// ---------------------------------------------------------------------------

function MetricPill({ label, metric }: { label: string; metric: UsageMetric }) {
  const { used, limit, unit } = metric;
  if (used == null) return null;

  const usedStr = `${formatNumber(used)}${limit == null && unit === "%" ? "%" : ""}`;
  const limitStr = limit != null ? ` / ${formatNumber(limit)} ${unit}` : unit === "%" ? "" : ` ${unit}`;

  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-muted-foreground/60">{label}</span>
      <span className="text-foreground font-semibold">{usedStr}</span>
      {limitStr && <span className="text-muted-foreground/50">{limitStr}</span>}
    </span>
  );
}

// ---------------------------------------------------------------------------
// StatBlock (quota only now — local overview uses strip instead)
// ---------------------------------------------------------------------------

function StatBlock({
  metric,
  label,
  title,
  compact = false,
}: {
  metric: UsageMetric;
  label: string;
  title: string;
  compact?: boolean;
}) {
  const valueStr =
    metric.used != null
      ? `${formatNumber(metric.used)}${metric.limit == null && metric.unit === "%" ? "%" : ""}`
      : "--";
  return (
    <div className={["rounded-lg bg-muted/30 border border-border/40", compact ? "px-3 py-2" : "py-3 px-2"].join(" ")}>
      <p className="text-lg md:text-2xl font-mono font-bold text-foreground">{valueStr}</p>
      {metric.limit != null && <p className="text-2xs text-muted-foreground font-mono">{formatLimit(metric.limit, metric.unit)}</p>}
      <p className="text-2xs text-muted-foreground/60 uppercase tracking-wider mt-1">{label}</p>
      {!compact && <p className="text-2xs text-muted-foreground mt-1">{title}</p>}
    </div>
  );
}
