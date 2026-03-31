import { useEffect, useState } from "react";
import MemberAvatar from "@/components/MemberAvatar";
import type { LeaseGroup } from "./session-list-utils";
import { calculateDuration, formatDuration } from "./utils/duration";
import { formatMetric } from "./utils/format";

const STATUS_CONFIG = {
  running: {
    dot: "bg-success animate-pulse",
    label: "运行中",
    border: "border-l-success/70",
    glow: "shadow-[0_0_0_1px_hsl(var(--success)/0.08)]",
  },
  paused: {
    dot: "bg-warning/80",
    label: "已暂停",
    border: "border-l-warning/50",
    glow: "",
  },
  stopped: {
    dot: "bg-muted-foreground/30",
    label: "已停止",
    border: "border-l-border/30",
    glow: "",
  },
  destroying: {
    dot: "bg-destructive animate-pulse",
    label: "销毁中",
    border: "border-l-destructive/70",
    glow: "",
  },
} as const;

interface SandboxCardProps {
  group: LeaseGroup;
  onClick: () => void;
}

export default function SandboxCard({ group, onClick }: SandboxCardProps) {
  const [duration, setDuration] = useState(() =>
    group.startedAt ? calculateDuration(group.startedAt) : null
  );

  // Tick duration every second only for running sandboxes
  useEffect(() => {
    if (group.status !== "running") return;
    const timer = setInterval(() => {
      setDuration(group.startedAt ? calculateDuration(group.startedAt) : null);
    }, 1000);
    return () => clearInterval(timer);
  }, [group.startedAt, group.status]);

  const cfg = STATUS_CONFIG[group.status] ?? STATUS_CONFIG.stopped;
  const isStopped = group.status === "stopped";
  const m = group.metrics;
  const hasMetrics =
    m != null &&
    (m.cpu != null || m.memory != null || m.memoryLimit != null || m.disk != null || m.diskLimit != null);

  return (
    <button
      onClick={onClick}
      className={[
        "group relative w-full text-left rounded-lg border border-border/50 border-l-2 bg-card/70",
        cfg.border,
        cfg.glow,
        "px-3 pt-2.5 pb-3 flex flex-col gap-2.5",
        "transition-all duration-fast ease-out-expo",
        "hover:border-primary/25 hover:bg-muted/20 hover:shadow-md hover:-translate-y-px",
        isStopped ? "opacity-45" : "",
      ].join(" ")}
    >
      {/* Top row: status + duration */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
          <span className="text-2xs font-mono font-bold text-muted-foreground tracking-widest">
            {cfg.label}
          </span>
        </div>
        {duration != null && (
          <span className="text-2xs font-mono text-muted-foreground/50 shrink-0">
            {formatDuration(duration)}
          </span>
        )}
      </div>

      {/* Agent stack */}
      <div className="flex items-center gap-2">
        <div className="flex -space-x-1.5 shrink-0">
          {group.sessions.slice(0, 3).map((s) => (
            <MemberAvatar key={s.id} name={s.memberName || "?"} avatarUrl={s.avatarUrl || undefined} size="xs" type="mycel_agent" className="border-2 border-card" />
          ))}
          {group.sessions.length > 3 && (
            <div className="w-6 h-6 rounded-full bg-muted border-2 border-card flex items-center justify-center text-3xs font-mono text-muted-foreground">
              +{group.sessions.length - 3}
            </div>
          )}
        </div>
        <span className="text-xs text-foreground truncate leading-snug">
          {group.sessions.map((s) => s.memberName || "未绑定").join(", ")}
        </span>
      </div>

      {/* Metrics mini-bar */}
      {hasMetrics && (
        <div className="grid grid-cols-3 gap-x-2 border-t border-border/20 pt-2 text-2xs font-mono">
          <MiniStat label="CPU" value={formatMetric(m?.cpu, "%")} />
          <MiniStat
            label="RAM"
            value={formatMetric(m?.memory, "GB")}
            sub={m?.memoryLimit != null ? `/${formatMetric(m.memoryLimit, "GB")}` : undefined}
          />
          <MiniStat
            label="Disk"
            value={formatMetric(m?.disk, "GB")}
            sub={m?.diskLimit != null ? `/${formatMetric(m.diskLimit, "GB")}` : undefined}
          />
        </div>
      )}

      {/* Lease ID footer */}
      {group.leaseId && (
        <p className="text-2xs font-mono text-muted-foreground/35 truncate -mt-1">
          {group.leaseId.length > 20 ? `${group.leaseId.slice(0, 20)}…` : group.leaseId}
        </p>
      )}
    </button>
  );
}

function MiniStat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div>
      <p className="text-3xs uppercase tracking-wider text-muted-foreground/40 mb-0.5">{label}</p>
      <p className="text-foreground leading-none">
        {value}
        {sub && <span className="text-muted-foreground/50">{sub}</span>}
      </p>
    </div>
  );
}
