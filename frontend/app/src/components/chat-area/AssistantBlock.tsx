import { memo } from "react";
import type { AssistantTurn, NoticeSegment, StreamStatus, ToolSegment, TurnSegment } from "../../api";
import MarkdownContent from "../MarkdownContent";
import { CopyButton } from "./CopyButton";
import { parseNoticeContent, STATUS_ICON } from "./NoticeBubble";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { ToolDetailBox } from "./ToolDetailBox";
import { formatTime } from "./utils";

// --- Phase splitting: segments → content phases + notice dividers ---

type ContentPhase = { kind: "content"; segments: TurnSegment[] };
type NoticePhase = { kind: "notice"; content: string };
type Phase = ContentPhase | NoticePhase;

function splitPhases(segments: TurnSegment[]): Phase[] {
  const phases: Phase[] = [];
  let buf: TurnSegment[] = [];
  for (const seg of segments) {
    if (seg.type === "notice") {
      if (buf.length > 0) { phases.push({ kind: "content", segments: buf }); buf = []; }
      phases.push({ kind: "notice", content: (seg as NoticeSegment).content });
    } else {
      buf.push(seg);
    }
  }
  if (buf.length > 0) phases.push({ kind: "content", segments: buf });
  return phases;
}

// --- Notice divider (inline within assistant block) ---

function NoticeDivider({ content }: { content: string }) {
  const parsed = parseNoticeContent(content);
  if (!parsed.text) return null;
  const icon = parsed.status ? STATUS_ICON[parsed.status] : null;
  return (
    <div className="flex items-center gap-3 my-2 select-none">
      <div className="flex-1 h-px bg-gray-100" />
      <span className="inline-flex items-center gap-1.5 px-2.5 text-[11px] text-gray-400">
        {icon}
        {parsed.text}
      </span>
      <div className="flex-1 h-px bg-gray-100" />
    </div>
  );
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

export const AssistantBlock = memo(function AssistantBlock({ entry, isStreamingThis, runtimeStatus, onFocusAgent }: AssistantBlockProps) {
  const hasNotice = entry.segments.some((s) => s.type === "notice");

  const fullText = entry.segments
    .filter((s) => s.type === "text")
    .map((s) => s.type === "text" ? s.content : "")
    .join("\n");

  const toolSegs = entry.segments.filter((s) => s.type === "tool") as ToolSegment[];
  const textSegs = entry.segments.filter((s) => s.type === "text");

  const hasVisible = toolSegs.length > 0 || textSegs.length > 0;

  if (!hasVisible && !isStreamingThis && !hasNotice) return null;

  return (
    <div className="flex gap-2.5 animate-fade-in group/block">
      <div className="w-6 h-6 rounded-full bg-[#171717] flex items-center justify-center flex-shrink-0 mt-0.5">
        <span className="text-[11px] font-semibold text-white">L</span>
      </div>
      <div className="flex-1 max-w-[calc(100%-36px)] space-y-1.5">
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
              ? <NoticeDivider key={`notice-${i}-${phase.content.slice(0, 32)}`} content={phase.content} />
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
          <div className="flex justify-start mt-0.5">
            <CopyButton text={fullText} />
          </div>
        )}
      </div>
    </div>
  );
});
