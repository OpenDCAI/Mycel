import { Monitor, Cloud, Container, X } from "lucide-react";
import type { ProviderInfo } from "./types";
import QuotaRing from "./QuotaRing";
import { CapabilityStrip } from "./CapabilityIcons";
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
  const cardCpu = provider.cardCpu;

  const runningSessions = sessions.filter((s) => s.status === "running");
  const pausedSessions = sessions.filter((s) => s.status === "paused");
  const stoppedSessions = sessions.filter((s) => s.status === "stopped");

  return (
    <button
      onClick={onSelect}
      disabled={isUnavailable}
      className={[
        "relative p-4 text-left transition-all duration-fast w-full rounded-xl border bg-card",
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
        <span className="text-xs text-muted-foreground">{typeLabel[type]}</span>
      </div>

      {/* Center: metrics (running + CPU if available) */}
      <div className="flex items-center justify-center min-h-[52px] mb-3 py-2 rounded-lg bg-muted/30">
        {isUnavailable ? (
          <div className="text-center">
            <p className="text-xs text-muted-foreground">未就绪</p>
            <p className="text-2xs text-muted-foreground/60 mt-0.5">
              {type === "container" ? "需要 Docker" : "需要安装 SDK"}
            </p>
          </div>
        ) : (
          <div className="flex items-center justify-center gap-6">
            <MetricCircle
              label="运行数"
              used={telemetry.running.used}
              limit={telemetry.running.limit}
              unit={telemetry.running.unit}
            />
            {/* Only show CPU ring if we have valid CPU data */}
            {(cardCpu.used != null || cardCpu.limit != null) && (
              <MetricCircle
                label="CPU"
                used={cardCpu.used}
                limit={cardCpu.limit}
                unit={cardCpu.unit}
                note={cardCpu.error}
              />
            )}
          </div>
        )}
      </div>

      {/* Capability icons */}
      <CapabilityStrip capabilities={provider.capabilities} />

      {/* Session dots — sorted running(green) → paused(yellow) → stopped(grey) */}
      {sessions.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2">
          {[...sessions]
            .sort((a, b) => {
              const order = { running: 0, destroying: 1, paused: 2, stopped: 3 };
              return (order[a.status] ?? 4) - (order[b.status] ?? 4);
            })
            .slice(0, 5)
            .map((s) => {
            const dotClass = {
              running: "bg-success animate-pulse",
              paused: "bg-warning/80",
              stopped: "bg-border",
              destroying: "bg-destructive animate-pulse",
            }[s.status] || "bg-border";

            return (
              <div
                key={s.id}
                className={`w-2 h-2 rounded-full ${dotClass}`}
              />
            );
          })}
          <span className="text-2xs text-muted-foreground ml-1">
            {runningSessions.length} 占用中
            {pausedSessions.length > 0 ? ` · ${pausedSessions.length} 暂停` : ""}
            {stoppedSessions.length > 0 ? ` · ${stoppedSessions.length} 已结束` : ""}
          </span>
        </div>
      )}
    </button>
  );
}

function MetricCircle({
  label,
  used,
  limit,
  unit,
  note,
}: {
  label: string;
  used: number | null;
  limit: number | null;
  unit: string;
  note?: string;
}) {
  const showRing = used != null && limit != null && limit > 0;
  return (
    <div className="text-center min-w-[64px]" title={note || undefined}>
      {showRing ? (
        <QuotaRing used={used} limit={limit} />
      ) : (
        <div className="w-12 h-12 rounded-full border border-border bg-card flex items-center justify-center mx-auto">
          <span className="text-xs font-mono font-semibold text-foreground">
            {used != null ? `${formatNumber(used)}${unit === "%" ? "%" : ""}` : "--"}
          </span>
        </div>
      )}
      <p className="text-2xs text-muted-foreground mt-1">{label}</p>
      {limit != null && <p className="text-2xs text-muted-foreground/60 font-mono">{formatLimit(limit, unit)}</p>}
    </div>
  );
}
