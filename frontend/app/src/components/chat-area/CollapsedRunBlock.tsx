import { ChevronRight, ChevronDown } from "lucide-react";
import { useState } from "react";
import type { AssistantTurn } from "../../api";
import { AssistantBlock } from "./AssistantBlock";

interface CollapsedRunBlockProps {
  runs: AssistantTurn[];
  onFocusAgent?: (taskId: string) => void;
}

// @@@aggregated-collapsed — one block for N consecutive external runs
export function CollapsedRunBlock({ runs, onFocusAgent }: CollapsedRunBlockProps) {
  const [expanded, setExpanded] = useState(false);

  const totalTools = runs.reduce((sum, r) => sum + r.segments.filter(s => s.type === "tool").length, 0);
  const senderName = runs[0]?.senderName || "external";
  const runCount = runs.length;

  const label = runCount === 1
    ? `${totalTools} tool${totalTools !== 1 ? "s" : ""}`
    : `${runCount} interactions · ${totalTools} tool${totalTools !== 1 ? "s" : ""}`;

  return (
    <div className="rounded-lg border border-border/60 bg-muted/30 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
      >
        {expanded
          ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground/60 shrink-0" />
          : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/60 shrink-0" />
        }
        <span className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground/70">{senderName}</span>
          {" "}{label}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-border/40 px-1 space-y-2 py-1">
          {runs.map(run => (
            <AssistantBlock
              key={run.id}
              entry={run}
              isStreamingThis={false}
              runtimeStatus={null}
              onFocusAgent={onFocusAgent}
            />
          ))}
        </div>
      )}
    </div>
  );
}
