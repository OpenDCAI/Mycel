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
  onFocusAgent?: (taskId: string) => void;
  onTaskNoticeClick?: (taskId: string) => void;
}

export default function ChatArea({ entries, isStreaming: _isStreaming, runtimeStatus, loading, onFocusAgent, onTaskNoticeClick }: ChatAreaProps) {
  const containerRef = useStickyScroll<HTMLDivElement>();

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto py-5 bg-white">
      {loading ? (
        <ChatSkeleton />
      ) : (
        <div className="max-w-3xl mx-auto px-5 space-y-3.5">
          {entries.map((entry) => {
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
            // @@@display-mode-routing — collapsed external runs get CollapsedRunBlock
            if (assistantEntry.displayMode === "collapsed") {
              return (
                <CollapsedRunBlock
                  key={entry.id}
                  entry={assistantEntry}
                  isStreamingThis={isStreamingThis}
                  onFocusAgent={onFocusAgent}
                />
              );
            }
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
