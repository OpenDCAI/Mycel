import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import MemberAvatar from "@/components/MemberAvatar";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import type { ResourceSession } from "./types";
import { calculateDuration, formatDuration } from "./utils/duration";
import { formatMetric } from "./utils/format";
import { SandboxFileBrowser } from "@/components/SandboxFileBrowser";
import { groupByLease, type LeaseGroup } from "./session-list-utils";

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

interface SessionListProps {
  sessions: ResourceSession[];
  providerType: string;
}

export default function SessionList({ sessions, providerType }: SessionListProps) {
  if (sessions.length === 0) {
    return <p className="text-xs text-muted-foreground">暂无会话</p>;
  }

  const groups = groupByLease(sessions);

  return (
    <div className="space-y-2">
      {groups.map((group) => (
        <LeaseItem key={group.leaseId || group.sessions.map((s) => s.id).join("|")} group={group} providerType={providerType} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LeaseItem
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<ResourceSession["status"], string> = {
  running: "运行中",
  paused: "已暂停",
  stopped: "已结束",
  destroying: "销毁中",
};

function LeaseItem({ group, providerType }: { group: LeaseGroup; providerType: string }) {
  const [expanded, setExpanded] = useState(false);
  const duration = group.startedAt ? calculateDuration(group.startedAt) : null;
  const isStopped = group.status === "stopped";
  const canBrowse = group.status !== "stopped" && group.status !== "destroying";

  const hasMetrics =
    group.metrics != null &&
    (group.metrics.cpu != null ||
     group.metrics.memory != null ||
     group.metrics.memoryLimit != null ||
     group.metrics.disk != null ||
     group.metrics.diskLimit != null);

  return (
    <div className={`rounded-md border border-border/50 bg-card/60 overflow-hidden ${isStopped ? "opacity-50" : ""}`}>
      {/* Row */}
      <button
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/20 transition-colors duration-fast text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <StatusDot status={group.status} />
        {expanded ? (
          <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
        )}

        {/* Crew avatars */}
        <div className="flex -space-x-1 shrink-0">
          {group.sessions.slice(0, 4).map((s) => (
            <MemberAvatar key={s.id} name={s.memberName || "?"} avatarUrl={s.avatarUrl || undefined} size="xs" type="mycel_agent" className="border border-background" />
          ))}
          {group.sessions.length > 4 && (
            <div className="w-5 h-5 rounded-full bg-muted border border-background flex items-center justify-center text-[8px] text-muted-foreground">
              +{group.sessions.length - 4}
            </div>
          )}
        </div>

        {/* Names */}
        <span className="text-xs text-foreground flex-1 truncate">
          {group.sessions.map((s) => s.memberName || "未绑定").join(", ")}
        </span>

        {/* Lease ID */}
        {group.leaseId && (
          <span className="text-[10px] text-muted-foreground font-mono shrink-0">
            {shortId(group.leaseId)}
          </span>
        )}

        {/* Duration + status */}
        <div className="flex items-center gap-2 shrink-0">
          {duration != null && (
            <span className="text-[10px] text-muted-foreground">{formatDuration(duration)}</span>
          )}
          <span className="text-[10px] text-muted-foreground">{STATUS_LABEL[group.status]}</span>
        </div>
      </button>

      {/* Expanded panel */}
      {expanded && (
        <div className="border-t border-border/30">
          {/* Metrics bar */}
          {hasMetrics && (
            <div className="grid grid-cols-3 gap-2 px-3 py-2 text-[10px] font-mono bg-muted/10 border-b border-border/20">
              <MetricCell label="CPU" used={group.metrics?.cpu} unit="%" />
              <MetricCell label="RAM" used={group.metrics?.memory} limit={group.metrics?.memoryLimit} unit="GB" note={group.metrics?.memoryNote} />
              <MetricCell label="磁盘" used={group.metrics?.disk} limit={group.metrics?.diskLimit} unit="GB" note={group.metrics?.diskNote} />
            </div>
          )}
          {/* File browser */}
          <div className="px-3 py-2">
            {canBrowse ? (
              <SandboxBrowser leaseId={group.leaseId} providerType={providerType} />
            ) : (
              <p className="text-[11px] text-muted-foreground text-center py-2">沙盒已停止，无法浏览文件</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sandbox file browser — uses shared SandboxFileBrowser component
// ---------------------------------------------------------------------------

function SandboxBrowser({ leaseId, providerType }: { leaseId: string; providerType: string }) {
  return <SandboxFileBrowser leaseId={leaseId} providerType={providerType} />;
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function StatusDot({ status }: { status: ResourceSession["status"] }) {
  const cls = {
    running: "bg-success animate-pulse",
    paused: "bg-warning/80",
    stopped: "bg-muted-foreground/40",
    destroying: "bg-destructive animate-pulse",
  }[status];
  return <span className={`h-2 w-2 rounded-full shrink-0 ${cls}`} />;
}

function MetricCell({
  label,
  used,
  limit,
  unit,
  note,
}: {
  label: string;
  used: number | null | undefined;
  limit?: number | null | undefined;
  unit: string;
  note?: string;
}) {
  const usedStr = used != null ? formatMetric(used, unit) : "--";
  const limitStr = limit != null ? formatMetric(limit, unit) : "--";

  // Show note icon if there's a note OR if limit is null (to explain why)
  const showNote = note != null && note.length > 0;

  return (
    <div className="rounded border border-border/40 bg-muted/20 px-2 py-1">
      <p className="text-muted-foreground">{label}</p>
      <p className="text-foreground font-semibold">
        {usedStr}
        {limit !== undefined && (
          <span className="text-muted-foreground font-normal"> / {limitStr}</span>
        )}
        {showNote && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="ml-1 text-muted-foreground cursor-help text-[9px] inline-block" style={{ userSelect: "none" }}>
                ⓘ
              </span>
            </TooltipTrigger>
            <TooltipContent>{note}</TooltipContent>
          </Tooltip>
        )}
      </p>
    </div>
  );
}

function shortId(raw: string): string {
  if (!raw) return "--";
  return raw.length <= 12 ? raw : `${raw.slice(0, 8)}…`;
}
