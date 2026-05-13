import { memo } from "react";
import { Loader2 } from "lucide-react";
import {
  isNoticeSegment,
  isRetrySegment,
  isTextSegment,
  isToolSegment,
  type AssistantTurn,
  type NotificationType,
  type StreamStatus,
  type TurnSegment,
} from "../../api";
import MarkdownContent from "../MarkdownContent";
import ActorAvatar from "../ActorAvatar";
import { CopyButton } from "./CopyButton";
import { InlineNotice } from "./NoticeBubble";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { ToolDetailBox } from "./ToolDetailBox";
import { formatTime } from "./utils";
import { AskUserQuestionCard } from "./AskUserQuestionCard";
import type { AskUserQuestionAnsweredPayload, AskUserQuestionPendingState } from "../../pages/ask-user-question";

// --- Phase splitting: segments → content phases + notice dividers ---

type ContentPhase = { kind: "content"; segments: TurnSegment[] };
type NoticePhase = { kind: "notice"; content: string; notificationType?: NotificationType };
type Phase = ContentPhase | NoticePhase;

function splitPhases(segments: TurnSegment[]): Phase[] {
  const phases: Phase[] = [];
  let buf: TurnSegment[] = [];
  for (const seg of segments) {
    if (isNoticeSegment(seg)) {
      if (buf.length > 0) { phases.push({ kind: "content", segments: buf }); buf = []; }
      phases.push({ kind: "notice", content: seg.content, notificationType: seg.notification_type });
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
  segments, allSegments, isStreaming, onFocusAgent, askUserQuestion,
}: {
  segments: TurnSegment[];
  /** All segments in the full turn (passed to DetailBoxModal). */
  allSegments?: TurnSegment[];
  isStreaming: boolean;
  onFocusAgent?: () => void;
  askUserQuestion?: { mode: "pending"; pending: AskUserQuestionPendingState } | { mode: "answered"; answered: AskUserQuestionAnsweredPayload };
}) {
  const toolSegs = segments.filter(isToolSegment);
  const visibleToolSegs = askUserQuestion
    ? toolSegs.filter((segment) => segment.step.name !== "AskUserQuestion")
    : toolSegs;
  const textSegs = segments.filter(isTextSegment);
  const visibleText = textSegs.length > 0 ? textSegs[textSegs.length - 1] : null;
  const retrySeg = segments.find(isRetrySegment);

  return (
    <>
      {visibleToolSegs.length > 0 && (
        <ToolDetailBox
          toolSegments={visibleToolSegs}
          isStreaming={isStreaming}
          allSegments={allSegments?.filter((segment) => segment.type !== "tool" || segment.step.name !== "AskUserQuestion")}
          onFocusAgent={onFocusAgent}
        />
      )}
      {askUserQuestion ? <AskUserQuestionCard {...askUserQuestion} /> : null}
      {visibleText && (
        <MarkdownContent content={visibleText.content} />
      )}
      {retrySeg && (
        <div className="text-xs text-warning mt-1.5 flex items-center gap-1.5">
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
  onFocusAgent?: () => void;
  agentName?: string;
  agentAvatarUrl?: string;
  askUserQuestion?: { mode: "pending"; pending: AskUserQuestionPendingState } | { mode: "answered"; answered: AskUserQuestionAnsweredPayload };
}

function formatDuration(ms: number): string {
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

export const AssistantBlock = memo(function AssistantBlock({ entry, isStreamingThis, runtimeStatus, onFocusAgent, agentName, agentAvatarUrl, askUserQuestion }: AssistantBlockProps) {
  const displayName = agentName || "Agent";
  const hasNotice = entry.segments.some((s) => s.type === "notice");

  const elapsed = entry.endTimestamp ? entry.endTimestamp - entry.timestamp : null;

  const fullText = entry.segments
    .filter(isTextSegment)
    .map((s) => s.content)
    .join("\n");

  const toolSegs = entry.segments.filter(isToolSegment);
  const textSegs = entry.segments.filter(isTextSegment);

  const hasVisible = toolSegs.length > 0 || textSegs.length > 0;

  if (!hasVisible && !isStreamingThis && !hasNotice) return null;

  const isBooting = isStreamingThis && !hasVisible && !runtimeStatus;

  return (
    <div className="flex gap-2.5 animate-fade-in group/block">
      <ActorAvatar name={displayName} avatarUrl={agentAvatarUrl} size="xs" type="mycel_agent" className={`mt-0.5${isBooting ? " avatar-booting" : ""}`} />
      <div className="flex-1 min-w-0 space-y-1.5 overflow-hidden">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">{displayName}</span>
          {entry.timestamp && (
            <span className="text-2xs text-muted-foreground/30">{formatTime(entry.timestamp)}</span>
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
                  key={phase.segments[0] && isToolSegment(phase.segments[0]) ? `tool-${phase.segments[0].step.id}` : `content-${i}`}
                  segments={phase.segments}
                  allSegments={entry.segments}
                  isStreaming={!!isStreamingThis}
                  onFocusAgent={onFocusAgent}
                  askUserQuestion={askUserQuestion}
                />
          )
        ) : (
          /* Original rendering path (no notices) */
          <ContentPhaseBlock
            segments={entry.segments}
            allSegments={entry.segments}
            isStreaming={!!isStreamingThis}
            onFocusAgent={onFocusAgent}
            askUserQuestion={askUserQuestion}
          />
        )}

        {!isStreamingThis && fullText.trim() && (
          <div className="flex items-center gap-2 mt-0.5">
            <CopyButton text={fullText} />
            {elapsed !== null && elapsed >= 1000 && (
              <span className="text-2xs text-muted-foreground/30 tabular-nums">{formatDuration(elapsed)}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
});
