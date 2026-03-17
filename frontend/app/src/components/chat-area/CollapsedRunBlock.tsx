import { ChevronRight, ChevronDown } from "lucide-react";
import { useState } from "react";
import type { AssistantTurn, ToolSegment } from "../../api";
import { AssistantBlock } from "./AssistantBlock";

interface CollapsedRunBlockProps {
  entry: AssistantTurn;
  isStreamingThis: boolean;
  onFocusAgent?: (taskId: string) => void;
}

// @@@tell-owner-extract — find tell_owner messages in collapsed run segments
function extractTellOwnerMessages(entry: AssistantTurn): string[] {
  const messages: string[] = [];
  for (const seg of entry.segments) {
    if (seg.type === "tool" && seg.step.name === "tell_owner") {
      const args = seg.step.args as { message?: string } | undefined;
      if (args?.message) messages.push(args.message);
    }
  }
  return messages;
}

export function CollapsedRunBlock({ entry, isStreamingThis, onFocusAgent }: CollapsedRunBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const toolCount = entry.segments.filter(s => s.type === "tool").length;
  const tellOwnerMessages = extractTellOwnerMessages(entry);
  const senderName = entry.senderName || "external";

  const duration = entry.endTimestamp
    ? Math.round((entry.endTimestamp - entry.timestamp) / 1000)
    : null;

  return (
    <div className="rounded-lg border border-border/60 bg-muted/30 overflow-hidden">
      {/* Collapsed header — click to expand/collapse */}
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
          {" "}
          {isStreamingThis ? "processing..." : (
            <>
              {toolCount > 0 && <>{toolCount} tool{toolCount !== 1 ? "s" : ""}</>}
              {duration !== null && <> · {duration}s</>}
            </>
          )}
        </span>
        {isStreamingThis && (
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse shrink-0" />
        )}
      </button>

      {/* Expanded: show full AssistantBlock content */}
      {expanded && (
        <div className="border-t border-border/40 px-1">
          <AssistantBlock
            entry={entry}
            isStreamingThis={isStreamingThis}
            runtimeStatus={null}
            onFocusAgent={onFocusAgent}
          />
        </div>
      )}

      {/* @@@punch-through — tell_owner messages always visible, amber highlight */}
      {tellOwnerMessages.map((msg, i) => (
        <div
          key={`tell-${i}`}
          className="mx-3 mb-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200/60 text-sm text-amber-900"
        >
          {msg}
        </div>
      ))}
    </div>
  );
}
