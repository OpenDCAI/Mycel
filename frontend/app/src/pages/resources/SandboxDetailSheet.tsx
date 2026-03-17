import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import MemberAvatar from "@/components/MemberAvatar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { SandboxFileBrowser } from "@/components/SandboxFileBrowser";
import type { LeaseGroup } from "./SessionList";
import type { ResourceSession, SessionMetrics } from "./types";
import { calculateDuration, formatDuration } from "./utils/duration";
import { formatMetric } from "./utils/format";

const STATUS_LABEL: Record<ResourceSession["status"], string> = {
  running: "运行中",
  paused: "已暂停",
  stopped: "已结束",
  destroying: "销毁中",
};

const STATUS_DOT: Record<ResourceSession["status"], string> = {
  running: "bg-success animate-pulse",
  paused: "bg-warning/80",
  stopped: "bg-muted-foreground/30",
  destroying: "bg-destructive animate-pulse",
};

interface SandboxDetailSheetProps {
  group: LeaseGroup | null;
  providerType: string;
  open: boolean;
  onClose: () => void;
}

export default function SandboxDetailSheet({
  group,
  providerType,
  open,
  onClose,
}: SandboxDetailSheetProps) {
  if (!group) return null;

  const duration = group.startedAt ? calculateDuration(group.startedAt) : null;
  const m = group.metrics;
  const hasMetrics =
    m != null &&
    (m.cpu != null || m.memory != null || m.memoryLimit != null || m.disk != null || m.diskLimit != null);
  const canBrowse = group.status !== "stopped" && group.status !== "destroying";

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        className="flex flex-col p-0 gap-0"
        // @@@sheet-width - override Radix default sm:max-w-sm (384px) to fit file browser comfortably
        style={{ width: "100%", maxWidth: "520px" }}
      >
        {/* Header */}
        <SheetHeader className="px-5 py-4 border-b border-border/60 shrink-0 gap-1">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[group.status]}`} />
            <span className="text-[11px] font-mono text-muted-foreground">
              {STATUS_LABEL[group.status]}
              {duration != null && ` · ${formatDuration(duration)}`}
            </span>
          </div>
          <SheetTitle className="text-sm font-mono text-foreground">
            {group.leaseId || "local"}
          </SheetTitle>
        </SheetHeader>

        {/* Agents + Metrics — scrollable middle section */}
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-5 py-4 space-y-5">
            {/* Agents */}
            <section>
              <p className="text-[9px] font-semibold text-muted-foreground/60 uppercase tracking-widest mb-2.5">
                Agents
              </p>
              <div className="space-y-2">
                {group.sessions.map((s) => (
                  <AgentRow key={s.id} session={s} />
                ))}
              </div>
            </section>

            {/* Metrics */}
            {hasMetrics && (
              <section>
                <p className="text-[9px] font-semibold text-muted-foreground/60 uppercase tracking-widest mb-2.5">
                  Metrics
                </p>
                <div className="grid grid-cols-3 gap-2">
                  <MetricBlock label="CPU" used={m?.cpu} unit="%" />
                  <MetricBlock label="RAM" used={m?.memory} limit={m?.memoryLimit} unit="GB" note={m?.memoryNote} />
                  <MetricBlock label="Disk" used={m?.disk} limit={m?.diskLimit} unit="GB" note={m?.diskNote} />
                </div>
              </section>
            )}
          </div>
        </ScrollArea>

        {/* File browser — fixed at bottom, flex-shrink-0 */}
        <div className="border-t border-border/50 shrink-0">
          <div className="px-5 pt-3 pb-1">
            <p className="text-[9px] font-semibold text-muted-foreground/60 uppercase tracking-widest">
              Files
            </p>
          </div>
          {canBrowse ? (
            <div className="px-5 pb-4">
              <SandboxFileBrowser
                leaseId={group.leaseId}
                providerType={providerType}
                className="h-[380px]"
              />
            </div>
          ) : (
            <p className="px-5 pb-4 text-xs text-muted-foreground">沙盒已停止，无法浏览文件</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function AgentRow({ session }: { session: ResourceSession }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/40 bg-muted/10 px-3 py-2.5">
      <MemberAvatar name={session.agentName || "?"} size="sm" type="mycel_agent" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">
          {session.agentName || "未绑定"}
        </p>
        <p className="text-[10px] font-mono text-muted-foreground/60 truncate mt-0.5">
          {session.threadId}
        </p>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[session.status]}`} />
        <span className="text-[10px] text-muted-foreground">{STATUS_LABEL[session.status]}</span>
      </div>
    </div>
  );
}

function MetricBlock({
  label,
  used,
  limit,
  unit,
  note,
}: {
  label: string;
  used?: number | null;
  limit?: number | null;
  unit: string;
  note?: string;
}) {
  const usedStr = formatMetric(used, unit);
  const limitStr = limit != null ? formatMetric(limit, unit) : null;
  return (
    <div className="rounded-md border border-border/40 bg-muted/15 px-2.5 py-2">
      <p className="text-[8px] text-muted-foreground/50 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-xs font-mono font-semibold text-foreground">
        {usedStr}
        {limitStr && <span className="text-muted-foreground/60 font-normal"> / {limitStr}</span>}
        {note && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="ml-1 text-muted-foreground/50 cursor-help text-[9px] inline-block">
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

// Re-export for consumers that only need the type
export type { SessionMetrics };
