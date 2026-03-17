import { useMemo } from "react";
import type { AssistantTurn, ChatEntry, NoticeMessage, StreamStatus } from "../api";
import { useStickyScroll } from "../hooks/use-sticky-scroll";
import { AssistantBlock } from "./chat-area/AssistantBlock";
import { ChatSkeleton } from "./chat-area/ChatSkeleton";
import { CollapsedRunBlock } from "./chat-area/CollapsedRunBlock";
import { NoticeBubble } from "./chat-area/NoticeBubble";
import { UserBubble } from "./chat-area/UserBubble";
import { WaterlineDivider } from "./chat-area/WaterlineDivider";

interface ChatAreaProps {
  entries: ChatEntry[];
  isStreaming: boolean;
  runtimeStatus: StreamStatus | null;
  loading?: boolean;
  showExternalRuns?: boolean;
  onFocusAgent?: (taskId: string) => void;
  onTaskNoticeClick?: (taskId: string) => void;
}

// @@@tell-owner-extract — pull tell_owner message from segments
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

type ProcessedEntry =
  | { type: "pass"; entry: ChatEntry }
  | { type: "tell_owner"; id: string; messages: string[] }
  | { type: "aggregated_collapsed"; id: string; runs: AssistantTurn[] };

// @@@preprocess — transform entries based on display mode
function preprocessEntries(entries: ChatEntry[], showExternalRuns: boolean): ProcessedEntry[] {
  const result: ProcessedEntry[] = [];

  for (const entry of entries) {
    if (entry.role !== "assistant") {
      result.push({ type: "pass", entry });
      continue;
    }

    const turn = entry as AssistantTurn;

    // punch_through: extract tell_owner messages, render as amber text
    if (turn.displayMode === "punch_through") {
      const msgs = extractTellOwnerMessages(turn);
      if (msgs.length > 0) {
        result.push({ type: "tell_owner", id: turn.id, messages: msgs });
      }
      continue;
    }

    // collapsed: hide by default, or aggregate when shown
    if (turn.displayMode === "collapsed") {
      // Always extract tell_owner even from collapsed turns
      const msgs = extractTellOwnerMessages(turn);
      if (msgs.length > 0) {
        result.push({ type: "tell_owner", id: `${turn.id}-tell`, messages: msgs });
      }

      if (!showExternalRuns) continue; // hidden by default

      // Aggregate with previous collapsed block if exists
      const prev = result[result.length - 1];
      if (prev?.type === "aggregated_collapsed") {
        prev.runs.push(turn);
      } else {
        result.push({ type: "aggregated_collapsed", id: turn.id, runs: [turn] });
      }
      continue;
    }

    // expanded / other: pass through
    result.push({ type: "pass", entry });
  }

  return result;
}

export default function ChatArea({ entries, isStreaming: _isStreaming, runtimeStatus, loading, showExternalRuns = false, onFocusAgent, onTaskNoticeClick }: ChatAreaProps) {
  const containerRef = useStickyScroll<HTMLDivElement>();

  const processed = useMemo(
    () => preprocessEntries(entries, showExternalRuns),
    [entries, showExternalRuns],
  );

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto py-5 bg-white">
      {loading ? (
        <ChatSkeleton />
      ) : (
        <div className="max-w-3xl mx-auto px-5 space-y-3.5">
          {processed.map((item) => {
            if (item.type === "tell_owner") {
              return (
                <div key={item.id} className="px-3 py-2 rounded-lg bg-amber-50 border border-amber-200/60 text-sm text-amber-900">
                  {item.messages.map((msg, i) => (
                    <p key={i}>{msg}</p>
                  ))}
                </div>
              );
            }

            if (item.type === "aggregated_collapsed") {
              return (
                <CollapsedRunBlock
                  key={item.id}
                  runs={item.runs}
                  onFocusAgent={onFocusAgent}
                />
              );
            }

            const entry = item.entry;
            if (entry.role === "notice") {
              return <NoticeBubble key={entry.id} entry={entry as NoticeMessage} onTaskNoticeClick={onTaskNoticeClick} />;
            }
            if (entry.role === "user") {
              return <UserBubble key={entry.id} entry={entry} />;
            }
            if (entry.role === "waterline") {
              return <WaterlineDivider key={entry.id} />;
            }
            const assistantEntry = entry as AssistantTurn;
            const isStreamingThis = assistantEntry.streaming === true;
            return (
              <AssistantBlock
                key={entry.id}
                entry={assistantEntry}
                isStreamingThis={isStreamingThis}
                runtimeStatus={isStreamingThis ? runtimeStatus : null}
                onFocusAgent={onFocusAgent}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
