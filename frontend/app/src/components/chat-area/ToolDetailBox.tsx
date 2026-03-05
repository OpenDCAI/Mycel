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
      return <Loader2 className="w-3 h-3 text-blue-500 animate-spin flex-shrink-0" />;
    case "done":
      return <CheckCircle2 className="w-3 h-3 text-[#a3a3a3] flex-shrink-0" />;
    case "error":
      return <XCircle className="w-3 h-3 text-red-500 flex-shrink-0" />;
    case "cancelled":
      return <XCircle className="w-3 h-3 text-[#a3a3a3] flex-shrink-0" />;
    default:
      return <CheckCircle2 className="w-3 h-3 text-[#a3a3a3] flex-shrink-0" />;
  }
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
        aria-label={`查看 ${toolCount} 个工具调用详情`}
        className={`rounded-lg border bg-[#fafafa] cursor-pointer transition-colors ${
          hasRunning ? "detail-box-glow" : "border-[#e5e5e5] hover:border-[#d4d4d4]"
        }`}
        onClick={() => setModalOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setModalOpen(true); } }}
        title="点击查看详情"
      >
        <div
          ref={scrollRef}
          className="relative z-[1] overflow-y-auto detail-box-scroll detail-box-mask px-2.5 py-1.5"
          style={{
            maxHeight: hasRunning ? 130 : 80,
            transition: "max-height 0.3s ease",
          }}
        >
          <div className="flex flex-col gap-0.5">
            {toolSegments.map((seg) => {
              const { step } = seg;
              const badge = TOOL_BADGE_STYLES[step.name] ?? { ...DEFAULT_BADGE, label: step.name };
              const isCalling = step.status === "calling";
              const isTaskStep = step.name === "Task" && !!onFocusAgent;

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
                    className={`inline-flex items-center px-1 py-0 rounded text-[10px] font-medium flex-shrink-0 ${badge.bg} ${badge.text}`}
                  >
                    {badge.label || step.name}
                  </span>
                  <span
                    className={`text-[11px] text-[#737373] font-mono truncate min-w-0 ${isCalling ? "animate-pulse-slow" : ""} ${
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
