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
  const primaryMetric = telemetry.quota ?? telemetry.cpu;
  const sourceCandidates = [telemetry.running.source, telemetry.quota?.source, telemetry.cpu.source];
  const displaySource = sourceCandidates.find((source) => source && source !== "unknown") ?? "unknown";

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

      {/* Center: quota ring or special state */}
      <div className="flex items-center justify-center min-h-[52px] mb-3 py-2 rounded-lg bg-muted/30">
        {type === "local" ? (
          <div className="text-center">
            <span className="text-2xl font-mono font-bold text-foreground">&infin;</span>
            <p className="text-[11px] text-muted-foreground">无限制</p>
          </div>
        ) : isUnavailable ? (
          <div className="text-center">
            <p className="text-xs text-muted-foreground">未就绪</p>
            <p className="text-[10px] text-muted-foreground/60 mt-0.5">需要 Docker</p>
          </div>
        ) : primaryMetric.used != null && primaryMetric.limit != null ? (
          <div className="text-center">
            <QuotaRing used={primaryMetric.used} limit={primaryMetric.limit} />
            <p className="text-[10px] text-muted-foreground mt-1">
              {telemetry.quota ? "配额使用" : "CPU 使用"}
            </p>
          </div>
        ) : (
          <div className="text-center">
            <span className="text-sm font-mono text-muted-foreground">
              {telemetry.running.used}
              {telemetry.running.limit != null ? `/${telemetry.running.limit}` : ""}
            </span>
            <p className="text-[10px] text-muted-foreground">运行数</p>
          </div>
        )}
      </div>

      {!isUnavailable && (
        <div className="mb-2">
          <span className="inline-flex rounded border border-border px-1.5 py-0.5 text-[9px] font-mono uppercase text-muted-foreground">
            src:{displaySource}
          </span>
        </div>
      )}

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
                s.status === "running" ? "bg-foreground" : s.status === "paused" ? "bg-warning/80" : "bg-border",
              ].join(" ")}
            />
          ))}
          <span className="text-[10px] text-muted-foreground ml-1">
            {runningSessions.length} 占用中
            {pausedSessions.length > 0 ? ` · ${pausedSessions.length} 已暂停` : ""}
            {stoppedSessions.length > 0 ? ` · ${stoppedSessions.length} 已结束` : ""}
          </span>
        </div>
      )}
    </button>
  );
}
