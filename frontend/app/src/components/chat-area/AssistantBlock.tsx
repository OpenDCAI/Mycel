import { memo, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import type { AssistantTurn, NoticeSegment, NotificationType, RetrySegment, StreamStatus, ToolSegment, TurnSegment } from "../../api";
import MarkdownContent from "../MarkdownContent";
import { CopyButton } from "./CopyButton";
import { InlineNotice } from "./NoticeBubble";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { ToolDetailBox } from "./ToolDetailBox";
import { formatTime } from "./utils";

// --- Phase splitting: segments → content phases + notice dividers ---

type ContentPhase = { kind: "content"; segments: TurnSegment[] };
type NoticePhase = { kind: "notice"; content: string; notificationType?: NotificationType };
type Phase = ContentPhase | NoticePhase;

function splitPhases(segments: TurnSegment[]): Phase[] {
  const phases: Phase[] = [];
  let buf: TurnSegment[] = [];
  for (const seg of segments) {
    if (seg.type === "notice") {
      if (buf.length > 0) { phases.push({ kind: "content", segments: buf }); buf = []; }
      const ns = seg as NoticeSegment;
      phases.push({ kind: "notice", content: ns.content, notificationType: ns.notification_type });
    } else {
      buf.push(seg);
    }
  }
  if (buf.length > 0) phases.push({ kind: "content", segments: buf });
  return phases;
}

// --- Notice divider (inline within assistant block) ---

function NoticeDivider({ content, notificationType }: { content: string; notificationType?: NotificationType }) {
  return <InlineNotice content={content} notificationType={notificationType} />;
}

// --- Content phase rendering (tools + final text) ---

function ContentPhaseBlock({
  segments, allSegments, isStreaming, onFocusAgent,
}: {
  segments: TurnSegment[];
  /** All segments in the full turn (passed to DetailBoxModal). */
  allSegments?: TurnSegment[];
  isStreaming: boolean;
  onFocusAgent?: (taskId: string) => void;
}) {
  const toolSegs = segments.filter((s) => s.type === "tool") as ToolSegment[];
  const textSegs = segments.filter((s) => s.type === "text");
  const visibleText = textSegs.length > 0 ? textSegs[textSegs.length - 1] : null;
  const retrySeg = segments.find((s) => s.type === "retry") as RetrySegment | undefined;

  return (
    <>
      {toolSegs.length > 0 && (
        <ToolDetailBox
          toolSegments={toolSegs}
          isStreaming={isStreaming}
          allSegments={allSegments}
          onFocusAgent={onFocusAgent}
        />
      )}
      {visibleText && visibleText.type === "text" && (
        <MarkdownContent content={visibleText.content} />
      )}
      {retrySeg && (
        <div className="text-xs text-amber-500 mt-1.5 flex items-center gap-1.5">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span>正在重试 {retrySeg.attempt}/{retrySeg.maxAttempts}...</span>
        </div>
      )}
    </>
  );
}

// --- Main component ---

interface AssistantBlockProps {
  entry: AssistantTurn;
  isStreamingThis?: boolean;
  runtimeStatus?: StreamStatus | null;
  onFocusAgent?: (taskId: string) => void;
}

function formatDuration(ms: number): string {
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

export const AssistantBlock = memo(function AssistantBlock({ entry, isStreamingThis, runtimeStatus, onFocusAgent }: AssistantBlockProps) {
  const hasNotice = entry.segments.some((s) => s.type === "notice");

  const [elapsed, setElapsed] = useState<number | null>(() =>
    entry.endTimestamp ? entry.endTimestamp - entry.timestamp : null
  );

  useEffect(() => {
    if (entry.endTimestamp) {
      setElapsed(entry.endTimestamp - entry.timestamp);
    }
  }, [entry.timestamp, entry.endTimestamp]);

  const fullText = entry.segments
    .filter((s) => s.type === "text")
    .map((s) => s.type === "text" ? s.content : "")
    .join("\n");

  const toolSegs = entry.segments.filter((s) => s.type === "tool") as ToolSegment[];
  const textSegs = entry.segments.filter((s) => s.type === "text");

  const hasVisible = toolSegs.length > 0 || textSegs.length > 0;

  if (!hasVisible && !isStreamingThis && !hasNotice) return null;

  const isBooting = isStreamingThis && !hasVisible && !runtimeStatus;

  return (
    <div className="flex gap-2.5 animate-fade-in group/block">
      <div className={`w-6 h-6 rounded-full bg-[#171717] flex items-center justify-center flex-shrink-0 mt-0.5${isBooting ? " avatar-booting" : ""}`}>
        <span className="text-[11px] font-semibold text-white">L</span>
      </div>
      <div className="flex-1 min-w-0 space-y-1.5 overflow-hidden">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-[#171717]">Leon</span>
          {entry.timestamp && (
            <span className="text-[10px] text-[#d4d4d4]">{formatTime(entry.timestamp)}</span>
          )}
        </div>

        {isStreamingThis && !hasVisible && (
          <ThinkingIndicator runtimeStatus={runtimeStatus} />
        )}

        {hasNotice ? (
          /* Phase-based rendering: split at notice boundaries */
          splitPhases(entry.segments).map((phase, i) =>
            phase.kind === "notice"
              ? <NoticeDivider key={`notice-${i}-${phase.content.slice(0, 32)}`} content={phase.content} notificationType={phase.notificationType} />
              : <ContentPhaseBlock
                  key={phase.segments[0]?.type === "tool" ? `tool-${(phase.segments[0] as ToolSegment).step.id}` : `content-${i}`}
                  segments={phase.segments}
                  allSegments={entry.segments}
                  isStreaming={!!isStreamingThis}
                  onFocusAgent={onFocusAgent}
                />
          )
        ) : (
          /* Original rendering path (no notices) */
          <ContentPhaseBlock
            segments={entry.segments}
            allSegments={entry.segments}
            isStreaming={!!isStreamingThis}
            onFocusAgent={onFocusAgent}
          />
        )}

        {!isStreamingThis && fullText.trim() && (
          <div className="flex items-center gap-2 mt-0.5">
            <CopyButton text={fullText} />
            {elapsed !== null && elapsed >= 1000 && (
              <span className="text-[10px] text-[#d4d4d4] tabular-nums">{formatDuration(elapsed)}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
});
