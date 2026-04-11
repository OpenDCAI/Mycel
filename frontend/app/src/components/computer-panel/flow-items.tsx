import { CheckCircle2, ChevronDown, ChevronRight, Loader2, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ToolStep } from "../../api";
import { DEFAULT_BADGE, TOOL_BADGE_STYLES } from "../chat-area/constants";
import { getStepSummary } from "../chat-area/utils";
import MarkdownContent from "../MarkdownContent";
import { ToolRenderer } from "../tool-renderers";
import type { FlowItem } from "./utils";

function getResultPreview(step: ToolStep): string | null {
  if (!step.result || step.status === "calling") return null;
  const firstLine = step.result.split("\n")[0].trim();
  if (!firstLine) return null;
  return firstLine.length > 100 ? firstLine.slice(0, 97) + "..." : firstLine;
}

/* -- FlowList: scrolling container for tool/text flow items -- */

interface FlowListProps {
  flowItems: FlowItem[];
  focusedStepId?: string | null;
  onFocusStep?: (id: string | null) => void;
  autoScroll?: boolean;
}

export function FlowList({
  flowItems,
  focusedStepId = null,
  onFocusStep,
  autoScroll = false,
}: FlowListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  // Track user scroll position: only auto-scroll if user is near bottom
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    isAtBottomRef.current = scrollHeight - scrollTop - clientHeight < 50;
  }, []);

  // Auto-scroll to focused step
  useEffect(() => {
    if (!focusedStepId || !scrollRef.current) return;
    const el = scrollRef.current.querySelector(`[data-step-id="${focusedStepId}"]`);
    if (el) {
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [focusedStepId]);

  // Auto-scroll to bottom when new items arrive (only if user hasn't scrolled up)
  useEffect(() => {
    if (!autoScroll || !scrollRef.current || !isAtBottomRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [autoScroll, flowItems]);

  if (flowItems.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-muted-foreground/70">
        暂无活动
      </div>
    );
  }

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto bg-background">
      <div className="px-3 py-2 space-y-1.5">
        {flowItems.map((item, i) =>
          item.type === "tool" ? (
            <ToolFlowLine
              key={item.step.id}
              step={item.step}
              isFocused={item.step.id === focusedStepId}
              onFocus={() => onFocusStep?.(item.step.id)}
            />
          ) : (
            <TextFlowLine key={`text-${item.turnId}-${i}`} content={item.content} />
          ),
        )}
      </div>
    </div>
  );
}

/* -- Tool flow line (borderless, replaces StepCard) -- */

function ToolFlowLine({
  step,
  isFocused,
  onFocus,
}: {
  step: ToolStep;
  isFocused: boolean;
  onFocus: () => void;
}) {
  const [userExpanded, setUserExpanded] = useState(false);
  const expanded = isFocused || userExpanded;
  const badge = TOOL_BADGE_STYLES[step.name] ?? { ...DEFAULT_BADGE, label: step.name };
  const preview = getResultPreview(step);

  return (
    <div
      data-step-id={step.id}
      className={isFocused ? "border-l-2 border-info/20 pl-2" : "pl-3"}
    >
      {/* Row: status icon + badge + summary + chevron */}
      <div
        className="flex items-center gap-1.5 cursor-pointer py-0.5"
        onClick={() => { setUserExpanded((v) => !v); onFocus(); }}
      >
        <StatusIcon status={step.status} />
        <span
          className={`inline-flex items-center px-1 py-0 rounded text-2xs font-medium flex-shrink-0 ${badge.bg} ${badge.text}`}
        >
          {badge.label || step.name}
        </span>
        <span className="text-xs text-muted-foreground font-mono truncate min-w-0 flex-1">
          {getStepSummary(step)}
        </span>
        {expanded
          ? <ChevronDown className="w-3 h-3 text-muted-foreground/70 flex-shrink-0" />
          : <ChevronRight className="w-3 h-3 text-muted-foreground/30 flex-shrink-0" />}
      </div>

      {/* Collapsed: 1-line result preview */}
      {!expanded && preview && (
        <div className="text-xs text-muted-foreground/70 font-mono truncate pl-5 -mt-0.5">
          → {preview}
        </div>
      )}

      {/* Expanded: renderer + full result */}
      {expanded && (
        <div className="pl-5 mt-1">
          <div className="text-xs">
            <ToolRenderer step={step} expanded={true} />
          </div>
          {step.result && (
            <pre className="mt-1.5 whitespace-pre-wrap break-words font-mono text-xs text-foreground-secondary bg-muted rounded p-2 max-h-[300px] overflow-y-auto">
              {step.result}
            </pre>
          )}
          {step.status === "cancelled" && !step.result && (
            <div className="mt-1 text-xs text-muted-foreground/70 italic">已取消</div>
          )}
        </div>
      )}
    </div>
  );
}

/* -- Text flow line (AI intermediate text, rendered as Markdown) -- */

function TextFlowLine({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = content.length > 300;

  if (!isLong || expanded) {
    return (
      <div className="pl-3">
        <MarkdownContent content={content} />
        {isLong && (
          <button
            className="text-xs text-muted-foreground/70 hover:text-muted-foreground mt-0.5"
            onClick={() => setExpanded(false)}
          >
            收起
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="pl-3 cursor-pointer" onClick={() => setExpanded(true)}>
      <MarkdownContent content={content.slice(0, 297) + "..."} />
      <span className="text-xs text-muted-foreground/70 hover:text-muted-foreground">展开</span>
    </div>
  );
}

/* -- Shared helpers -- */

function StatusIcon({ status }: { status: ToolStep["status"] }) {
  switch (status) {
    case "calling":
      return <Loader2 className="w-3.5 h-3.5 text-info animate-spin flex-shrink-0" />;
    case "done":
      return <CheckCircle2 className="w-3.5 h-3.5 text-muted-foreground/70 flex-shrink-0" />;
    case "error":
      return <XCircle className="w-3.5 h-3.5 text-destructive flex-shrink-0" />;
    case "cancelled":
      return <XCircle className="w-3.5 h-3.5 text-muted-foreground/70 flex-shrink-0" />;
  }
}
