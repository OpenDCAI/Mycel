import { Monitor, Cloud, Container, Lock, Settings, ArrowRight, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import type { AllocatedResource, ProviderInfo, ResourceSession, UsageMetric } from "./types";
import ResourceAllocation from "./ResourceAllocation";

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
  allocatedResources: AllocatedResource[];
}

export default function ProviderDetail({ provider, allocatedResources }: ProviderDetailProps) {
  const { name, description, vendor, type, status, unavailableReason, telemetry, error } = provider;
  const TypeIcon = typeIcon[type];

  if (status === "unavailable") {
    return (
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/20">
          <div className="flex items-center gap-3">
            <TypeIcon className="w-4 h-4 text-muted-foreground" />
            <div>
              <h3 className="text-sm font-semibold text-foreground">{name}</h3>
              <p className="text-[11px] text-muted-foreground">{description}</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">{typeLabel[type]}</span>
            <span className="text-[11px] text-muted-foreground">·</span>
            <span className="text-[11px] text-muted-foreground">{statusLabel[status]}</span>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center py-12 px-6">
          <Lock className="w-8 h-8 text-muted-foreground/40 mb-3" />
          <p className="text-sm text-muted-foreground mb-1">{unavailableReason}</p>
          {error?.message && <p className="text-xs text-muted-foreground/70 mb-2 font-mono">{error.message}</p>}
          <p className="text-xs text-muted-foreground mb-4">前往 设置 &gt; 沙箱 配置 {name} 环境</p>
          <Link
            to="/settings"
            className="inline-flex items-center gap-1.5 text-xs text-foreground hover:text-primary transition-colors border border-border rounded-lg px-3 py-1.5"
          >
            <Settings className="w-3 h-3" />
            前往设置
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/20">
        <div className="flex items-center gap-3">
          <TypeIcon className="w-4 h-4 text-muted-foreground" />
          <div>
            <h3 className="text-sm font-semibold text-foreground">{name}</h3>
            <p className="text-[11px] text-muted-foreground">
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
              className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground"
            >
              控制台
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
          <span className="text-[11px] text-muted-foreground">{typeLabel[type]}</span>
          <span className="text-[11px] text-muted-foreground">·</span>
          <span className={`text-[11px] ${status === "active" ? "text-success" : "text-muted-foreground"}`}>
            {statusLabel[status]}
          </span>
        </div>
      </div>

      <div className="p-5">
        <div className="mb-1">
          <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium">概览</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          <StatBlock metric={telemetry.running} label="running" title="运行数" />
          <StatBlock metric={telemetry.cpu} label="cpu" title="CPU" />
          <StatBlock metric={telemetry.memory} label="memory" title="内存" />
          <StatBlock metric={telemetry.disk} label="disk" title="磁盘" />
        </div>

        {telemetry.quota && (
          <div className="mb-5">
            <div className="mb-2">
              <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium">配额</span>
            </div>
            <div className="rounded-lg bg-muted/15 border border-border/40 p-3">
              <StatBlock metric={telemetry.quota} label="quota" title="额度" compact />
            </div>
          </div>
        )}

        <div className="mb-5">
          <div className="mb-2">
            <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium">沙盒列表</span>
          </div>
          <div className="rounded-lg bg-muted/15 border border-border/40 p-3">
            <SessionMetricsList sessions={provider.sessions} />
          </div>
        </div>

        <div>
          <div className="mb-2">
            <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium">资源分配</span>
          </div>
          <div className="rounded-lg bg-muted/15 border border-border/40 p-3">
            <ResourceAllocation resources={allocatedResources} providerId={provider.id} />
          </div>
        </div>
      </div>
    </div>
  );
}

function SessionMetricsList({ sessions }: { sessions: ResourceSession[] }) {
  const activeSessions = sessions.filter((session) => session.status !== "stopped");
  if (activeSessions.length === 0) {
    return <p className="text-xs text-muted-foreground">暂无运行中/暂停会话</p>;
  }

  return (
    <div className="space-y-2">
      {activeSessions.map((session) => (
        <div key={session.id} className="rounded-md border border-border/50 bg-card/60 px-3 py-2">
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="flex items-center gap-2">
              <StatusDot status={session.status} />
              <span className="text-xs text-foreground font-medium">{session.agentName || "未绑定Agent"}</span>
              <span className="text-[10px] text-muted-foreground font-mono">{shortId(session.threadId)}</span>
            </div>
            <span className="text-[10px] text-muted-foreground font-mono">{session.status}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
            <MetricCell label="CPU" value={session.metrics?.cpu} unit="%" />
            <MetricCell label="RAM" value={session.metrics?.memory} unit="GB" />
            <MetricCell label="磁盘" value={session.metrics?.disk} unit="GB" />
          </div>
        </div>
      ))}
    </div>
  );
}

function StatusDot({ status }: { status: ResourceSession["status"] }) {
  return (
    <span
      className={[
        "h-2 w-2 rounded-full",
        status === "running" ? "bg-success" : status === "paused" ? "bg-warning/80" : "bg-muted-foreground/40",
      ].join(" ")}
    />
  );
}

function MetricCell({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | null | undefined;
  unit: string;
}) {
  return (
    <div className="rounded border border-border/40 bg-muted/20 px-2 py-1">
      <p className="text-muted-foreground">{label}</p>
      <p className="text-foreground font-semibold">{formatMetricValue(value, unit)}</p>
    </div>
  );
}

function formatMetricValue(value: number | null | undefined, unit: string): string {
  if (value == null) {
    return "--";
  }
  const show = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
  return `${show}${unit}`;
}

function shortId(raw: string): string {
  if (!raw) {
    return "--";
  }
  return raw.length <= 12 ? raw : `${raw.slice(0, 8)}...`;
}

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
  return (
    <div className={["rounded-lg bg-muted/30 border border-border/40", compact ? "px-3 py-2" : "py-3 px-2"].join(" ")}>
      <p className="text-lg md:text-2xl font-mono font-bold text-foreground">{formatUsed(metric.used)}</p>
      <p className="text-[10px] text-muted-foreground font-mono">{formatLimit(metric.limit, metric.unit)}</p>
      <p className="text-[9px] text-muted-foreground/60 uppercase tracking-wider mt-1">{label}</p>
      {!compact && <p className="text-[10px] text-muted-foreground mt-1">{title}</p>}
    </div>
  );
}

function formatUsed(value: number | null): string {
  if (value == null) {
    return "Unknown";
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(1).replace(/\.0$/, "");
}

function formatLimit(limit: number | null, unit: string): string {
  if (limit == null) {
    return `limit: Unknown ${unit}`;
  }
  const show = Number.isInteger(limit) ? String(limit) : limit.toFixed(1).replace(/\.0$/, "");
  return `limit: ${show} ${unit}`;
}
