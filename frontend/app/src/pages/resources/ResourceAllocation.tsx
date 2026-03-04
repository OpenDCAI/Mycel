import { Bot } from "lucide-react";
import type { AllocatedResource, ResourceType } from "./types";
import { CAPABILITY_LABELS, CAPABILITY_KEYS } from "./capabilities";
import { CAPABILITY_ICON_MAP } from "./CapabilityIcons";

interface ResourceAllocationProps {
  /** All allocated resources (across all providers or filtered to one) */
  resources: AllocatedResource[];
  /** If set, only show resources of this provider */
  providerId?: string;
}

/** Group resources by type, then show allocations per type */
export default function ResourceAllocation({ resources, providerId }: ResourceAllocationProps) {
  const filtered = providerId ? resources.filter((r) => r.providerId === providerId) : resources;

  // Group by resource type
  const byType = new Map<ResourceType, AllocatedResource[]>();
  for (const r of filtered) {
    const list = byType.get(r.resourceType) || [];
    list.push(r);
    byType.set(r.resourceType, list);
  }

  // Also track which resource types the provider supports but have no allocations
  const allTypes = CAPABILITY_KEYS as readonly string[];

  return (
    <div className="space-y-1">
      {allTypes.map((key) => {
        const Icon = CAPABILITY_ICON_MAP[key];
        const allocations = byType.get(key as ResourceType) || [];
        const activeCount = allocations.filter((a) => a.sessionStatus === "running").length;

        return (
          <div
            key={key}
            className={[
              "flex items-center gap-3 px-3 py-2 rounded-lg transition-colors",
              allocations.length > 0 ? "bg-foreground/[0.02]" : "",
            ].join(" ")}
          >
            {/* Resource icon + name */}
            <div className="flex items-center gap-2 w-16 shrink-0">
              <div
                className={[
                  "w-6 h-6 rounded-md flex items-center justify-center shrink-0",
                  allocations.length > 0
                    ? "bg-foreground/8 text-foreground"
                    : "bg-muted text-muted-foreground/40",
                ].join(" ")}
              >
                <Icon className="w-3.5 h-3.5" />
              </div>
              <span
                className={[
                  "text-xs",
                  allocations.length > 0 ? "text-foreground font-medium" : "text-muted-foreground/50",
                ].join(" ")}
              >
                {CAPABILITY_LABELS[key]}
              </span>
            </div>

            {/* Allocations: agent badges */}
            <div className="flex-1 flex items-center gap-1.5 flex-wrap min-h-[24px]">
              {allocations.length === 0 ? (
                <span className="text-[10px] text-muted-foreground/40">--</span>
              ) : (
                allocations.map((a) => (
                  <AgentBadge key={`${a.sessionId}-${a.resourceType}`} allocation={a} />
                ))
              )}
            </div>

            {/* Count */}
            {allocations.length > 0 && (
              <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                {activeCount > 0 && (
                  <span className="text-success">{activeCount} 活跃</span>
                )}
                {activeCount > 0 && allocations.length > activeCount && " · "}
                {allocations.length > activeCount && (
                  <span>{allocations.length - activeCount} 暂停</span>
                )}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function AgentBadge({ allocation }: { allocation: AllocatedResource }) {
  const isRunning = allocation.sessionStatus === "running";

  return (
    <div
      className={[
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] border transition-colors",
        isRunning
          ? "bg-foreground/[0.04] border-foreground/10 text-foreground"
          : "bg-muted/50 border-border/50 text-muted-foreground",
      ].join(" ")}
    >
      <Bot className="w-3 h-3 shrink-0" />
      <span className="font-medium">{allocation.agentName}</span>
      <span className="text-[9px] text-muted-foreground">{allocation.providerName}</span>
      {allocation.threadId && (
        <span className="text-[9px] font-mono text-muted-foreground/80" title={allocation.threadId}>
          {shortThreadId(allocation.threadId)}
        </span>
      )}
      <div
        className={[
          "w-1.5 h-1.5 rounded-full shrink-0",
          isRunning ? "bg-success animate-pulse-slow" : "bg-muted-foreground/30",
        ].join(" ")}
      />
    </div>
  );
}

function shortThreadId(threadId: string): string {
  if (threadId.length <= 8) return threadId;
  return `${threadId.slice(0, 8)}...`;
}
