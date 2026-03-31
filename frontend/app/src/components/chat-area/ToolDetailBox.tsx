import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";
import type { ToolSegment, TurnSegment } from "../../api";
import { DEFAULT_BADGE, TOOL_BADGE_STYLES } from "./constants";
import { DetailBoxModal } from "./DetailBoxModal";
import { getStepSummary } from "./utils";

interface ToolDetailBoxProps {
  toolSegments: ToolSegment[];
  isStreaming: boolean;
  /** All segments in the turn (for Modal detail view). */
  allSegments?: TurnSegment[];
  onFocusAgent?: (stepId: string) => void;
}

function MiniStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "calling":
      return <Loader2 className="w-3 h-3 text-info animate-spin flex-shrink-0" />;
    case "done":
      return <CheckCircle2 className="w-3 h-3 text-muted-foreground/70 flex-shrink-0" />;
    case "error":
      return <XCircle className="w-3 h-3 text-destructive flex-shrink-0" />;
    case "cancelled":
      return <XCircle className="w-3 h-3 text-muted-foreground/70 flex-shrink-0" />;
    default:
      return <CheckCircle2 className="w-3 h-3 text-muted-foreground/70 flex-shrink-0" />;
  }
}

/** Slot-machine style rolling number — digits slide up on increment. */
function RollingNumber({ value }: { value: number }) {
  const prevRef = useRef(value);
  const [display, setDisplay] = useState({ curr: value, prev: null as number | null, tick: 0 });

  useEffect(() => {
    if (value === prevRef.current) return;
    const prev = prevRef.current;
    prevRef.current = value;
    setDisplay(d => ({ curr: value, prev, tick: d.tick + 1 }));
  }, [value]);

  const { curr, prev, tick } = display;
  const digits = String(curr).length;

  return (
    <span
      style={{
        position: "relative",
        display: "inline-block",
        overflow: "hidden",
        verticalAlign: "middle",
        height: "1.1em",
        minWidth: `${digits * 0.62}em`,
        lineHeight: 1,
      }}
    >
      {/* Exiting number — slides out upward */}
      {prev !== null && tick > 0 && (
        <span
          key={`out-${tick}`}
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            animation: "numRollOut var(--duration-fast) var(--ease-in) forwards",
          }}
        >
          {prev}
        </span>
      )}
      {/* Entering number — rolls in from below */}
      <span
        key={`in-${tick}`}
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          animation: tick > 0 ? "numRollIn var(--duration-normal) var(--ease-out) forwards" : "none",
        }}
      >
        {curr}
      </span>
    </span>
  );
}

export const ToolDetailBox = memo(function ToolDetailBox({
  toolSegments,
  isStreaming,
  allSegments,
  onFocusAgent,
}: ToolDetailBoxProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [toolSegments.length]);

  const hasRunning = isStreaming || toolSegments.some((s) => s.step.status === "calling");
  const toolCount = toolSegments.length;

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        aria-label={`查看 ${toolCount} 次工具调用详情`}
        className={`relative rounded-lg border bg-muted cursor-pointer transition-colors duration-fast ${
          hasRunning ? "detail-box-glow" : "border-border hover:border-border"
        }`}
        onClick={() => setModalOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setModalOpen(true); } }}
        title="点击查看详情"
      >
        {/* Rolling count badge — top-right corner */}
        <div className="absolute top-1.5 right-2 z-10 flex items-center gap-0.5 pointer-events-none select-none">
          <span className="text-2xs text-muted-foreground tabular-nums leading-none font-medium">
            <RollingNumber value={toolCount} />
          </span>
          <span className="text-2xs text-muted-foreground leading-none"> 次工具</span>
        </div>

        <div
          ref={scrollRef}
          className="relative z-[1] overflow-y-auto detail-box-scroll detail-box-mask px-2.5 py-1.5 pr-16"
          style={{
            maxHeight: hasRunning ? 130 : 80,
            transition: "max-height var(--duration-normal) var(--ease-default)",
          }}
        >
          <div className="flex flex-col gap-0.5">
            {toolSegments.map((seg) => {
              const { step } = seg;
              const badge = TOOL_BADGE_STYLES[step.name] ?? { ...DEFAULT_BADGE, label: step.name };
              const isCalling = step.status === "calling";
              const isTaskStep = step.name === "Agent" && !!onFocusAgent;

              return (
                <div
                  key={step.id}
                  className={`flex items-center gap-1.5 h-6 min-w-0 animate-fade-in ${
                    isTaskStep ? "cursor-pointer hover:bg-black/[0.03] rounded -mx-0.5 px-0.5" : ""
                  }`}
                  onClick={isTaskStep ? (e) => { e.stopPropagation(); onFocusAgent(step.id); } : undefined}
                >
                  <MiniStatusIcon status={step.status} />
                  <span
                    className={`inline-flex items-center px-1 py-0 rounded text-2xs font-medium flex-shrink-0 ${badge.bg} ${badge.text}`}
                  >
                    {badge.label || step.name}
                  </span>
                  <span
                    className={`text-xs text-muted-foreground font-mono truncate min-w-0 ${isCalling ? "animate-pulse-slow" : ""} ${
                      isTaskStep ? "underline decoration-dotted underline-offset-2" : ""
                    }`}
                  >
                    {getStepSummary(step)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <DetailBoxModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        segments={allSegments ?? toolSegments}
      />
    </>
  );
});
