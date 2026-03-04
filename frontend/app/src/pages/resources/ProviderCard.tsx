import { Monitor, Cloud, Container, X } from "lucide-react";
import type { ProviderInfo } from "./types";
import QuotaRing from "./QuotaRing";
import { CapabilityStrip } from "./CapabilityIcons";

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

interface ProviderCardProps {
  provider: ProviderInfo;
  selected: boolean;
  onSelect: () => void;
}

export default function ProviderCard({ provider, selected, onSelect }: ProviderCardProps) {
  const { status, type, name, sessions, telemetry } = provider;
  const isUnavailable = status === "unavailable";
  const isActive = status === "active";
  const TypeIcon = typeIcon[type];
  const secondary = resolveSecondaryMetric(provider);

  const runningSessions = sessions.filter((s) => s.status === "running");
  const pausedSessions = sessions.filter((s) => s.status === "paused");
  const stoppedSessions = sessions.filter((s) => s.status === "stopped");

  return (
    <button
      onClick={onSelect}
      disabled={isUnavailable}
      className={[
        "relative p-4 text-left transition-all w-full rounded-xl border bg-card",
        selected
          ? "border-primary/30 glow-sm shadow-md ring-1 ring-primary/10"
          : "border-border hover:border-primary/20 hover:shadow-sm",
        isActive && !selected ? "shadow-sm" : "",
        isUnavailable ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
      ].join(" ")}
    >
      {/* Header: status light + name */}
      <div className="flex items-center gap-2 mb-1">
        <div
          className={[
            "w-2 h-2 rounded-full shrink-0",
            isActive ? "bg-success animate-pulse-slow" : "",
            status === "ready" ? "bg-muted-foreground/40" : "",
            isUnavailable ? "bg-transparent" : "",
          ].join(" ")}
        >
          {isUnavailable && <X className="w-2 h-2 text-muted-foreground" />}
        </div>
        <span className="text-sm font-semibold text-foreground truncate">{name}</span>
      </div>

      {/* Separator */}
      <div className="border-t border-dashed border-border my-2" />

      {/* Type label */}
      <div className="flex items-center gap-1.5 mb-3">
        <TypeIcon className="w-3 h-3 text-muted-foreground" />
        <span className="text-[11px] text-muted-foreground">{typeLabel[type]}</span>
      </div>

      {/* Center: fixed dual metrics (running + runtime metric) */}
      <div className="flex items-center justify-center min-h-[52px] mb-3 py-2 rounded-lg bg-muted/30">
        {isUnavailable ? (
          <div className="text-center">
            <p className="text-xs text-muted-foreground">未就绪</p>
            <p className="text-[10px] text-muted-foreground/60 mt-0.5">需要 Docker</p>
          </div>
        ) : (
          <div className="flex items-center justify-center gap-6">
            <MetricCircle
              label="运行数"
              used={telemetry.running.used}
              limit={telemetry.running.limit}
              unit={telemetry.running.unit}
            />
            <MetricCircle
              label={secondary.label}
              used={secondary.used}
              limit={secondary.limit}
              unit={secondary.unit}
            />
          </div>
        )}
      </div>

      {/* Capability icons */}
      <CapabilityStrip capabilities={provider.capabilities} />

      {/* Session dots */}
      {sessions.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2">
          {sessions.slice(0, 5).map((s) => (
            <div
              key={s.id}
              className={[
                "w-2 h-2 rounded-full",
                s.status === "running" ? "bg-success" : s.status === "paused" ? "bg-warning/80" : "bg-border",
              ].join(" ")}
            />
          ))}
          <span className="text-[10px] text-muted-foreground ml-1">
            {runningSessions.length} 占用中
            {pausedSessions.length > 0 ? ` · ${pausedSessions.length} 暂停(不占用)` : ""}
            {stoppedSessions.length > 0 ? ` · ${stoppedSessions.length} 已结束` : ""}
          </span>
        </div>
      )}
    </button>
  );
}

function resolveSecondaryMetric(provider: ProviderInfo): {
  label: string;
  used: number | null;
  limit: number | null;
  unit: string;
} {
  const cpu = provider.telemetry.cpu;
  // @@@cloud-cpu-guardrail - cloud card must not display locally aggregated CPU as quota-like truth; show placeholder until real provider quota signal is available.
  if (provider.type === "cloud") {
    return {
      label: "CPU",
      used: null,
      limit: null,
      unit: cpu.unit,
    };
  }
  return {
    label: "CPU",
    used: cpu.used,
    limit: cpu.limit,
    unit: cpu.unit,
  };
}

function MetricCircle({
  label,
  used,
  limit,
  unit,
}: {
  label: string;
  used: number | null;
  limit: number | null;
  unit: string;
}) {
  const showRing = used != null && limit != null && limit > 0;
  return (
    <div className="text-center min-w-[64px]">
      {showRing ? (
        <QuotaRing used={used} limit={limit} />
      ) : (
        <div className="w-12 h-12 rounded-full border border-border bg-card flex items-center justify-center mx-auto">
          <span className="text-xs font-mono font-semibold text-foreground">{formatUsed(used)}</span>
        </div>
      )}
      <p className="text-[10px] text-muted-foreground mt-1">{label}</p>
      <p className="text-[9px] text-muted-foreground/60 font-mono">{formatLimit(limit, unit)}</p>
    </div>
  );
}

function formatUsed(value: number | null): string {
  if (value == null) {
    return "--";
  }
  if (Number.isInteger(value)) {
    return String(value);
  }
  return value.toFixed(1).replace(/\.0$/, "");
}

function formatLimit(limit: number | null, unit: string): string {
  if (limit == null) {
    return `limit: -- ${unit}`;
  }
  const show = Number.isInteger(limit) ? String(limit) : limit.toFixed(1).replace(/\.0$/, "");
  return `limit: ${show} ${unit}`;
}
