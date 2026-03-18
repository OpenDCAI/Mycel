import type { AssistantTurn, ChatEntry, NoticeMessage, StreamStatus } from "../api";
import { useStickyScroll } from "../hooks/use-sticky-scroll";
import { AssistantBlock } from "./chat-area/AssistantBlock";
import { ChatSkeleton } from "./chat-area/ChatSkeleton";
import { NoticeBubble } from "./chat-area/NoticeBubble";
import { UserBubble } from "./chat-area/UserBubble";

interface ChatAreaProps {
  entries: ChatEntry[];
  isStreaming: boolean;
  runtimeStatus: StreamStatus | null;
  loading?: boolean;
  onFocusAgent?: (taskId: string) => void;
  onTaskNoticeClick?: (taskId: string) => void;
  agentName?: string;
  agentAvatarUrl?: string;
  userName?: string;
  userAvatarUrl?: string;
}

export default function ChatArea({ entries, isStreaming: _isStreaming, runtimeStatus, loading, onFocusAgent, onTaskNoticeClick, agentName, agentAvatarUrl, userName, userAvatarUrl }: ChatAreaProps) {
  const containerRef = useStickyScroll<HTMLDivElement>();

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto py-5 bg-white">
      {loading ? (
        <ChatSkeleton />
      ) : (
        <div className="max-w-3xl mx-auto px-5 space-y-3.5">
          {entries.map((entry) => {
            const isHidden = "showing" in entry && entry.showing === false;
            if (entry.role === "notice") {
              return <NoticeBubble key={entry.id} entry={entry as NoticeMessage} onTaskNoticeClick={onTaskNoticeClick} />;
            }
            if (entry.role === "user") {
              return (
                <div key={entry.id} className={isHidden ? "opacity-40" : ""}>
                  {isHidden && entry.senderName && (
                    <div className="text-[10px] text-[#a3a3a3] mb-0.5 text-right mr-2">{entry.senderName}</div>
                  )}
                  <UserBubble entry={entry} userName={isHidden ? (entry.senderName || "external") : userName} avatarUrl={isHidden ? undefined : userAvatarUrl} />
                </div>
              );
            }
            const assistantEntry = entry as AssistantTurn;
            const isStreamingThis = assistantEntry.streaming === true;
            return (
              <div key={entry.id} className={isHidden ? "opacity-40" : ""}>
                <AssistantBlock
                  entry={assistantEntry}
                  isStreamingThis={isStreamingThis}
                  runtimeStatus={isStreamingThis ? runtimeStatus : null}
                  onFocusAgent={onFocusAgent}
                  agentName={agentName}
                  agentAvatarUrl={agentAvatarUrl}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
