import type { AssistantTurn, ChatEntry, NoticeMessage, StreamStatus } from "../api";
import { useStickyScroll } from "../hooks/use-sticky-scroll";
import type { AskUserQuestionPendingState } from "../pages/ask-user-question";
import { parseAskUserQuestionAnswerPayload } from "../pages/ask-user-question";
import { AssistantBlock } from "./chat-area/AssistantBlock";
import { ChatSkeleton } from "./chat-area/ChatSkeleton";
import { NoticeBubble } from "./chat-area/NoticeBubble";
import { UserBubble } from "./chat-area/UserBubble";

interface ChatAreaProps {
  entries: ChatEntry[];
  runtimeStatus: StreamStatus | null;
  loading?: boolean;
  onFocusAgent?: (taskId: string) => void;
  onTaskNoticeClick?: (taskId: string) => void;
  agentName?: string;
  agentAvatarUrl?: string;
  userName?: string;
  userAvatarUrl?: string;
  askUserQuestion?: AskUserQuestionPendingState;
}

function hasAskUserQuestionTool(entry: AssistantTurn): boolean {
  return entry.segments.some((segment) => segment.type === "tool" && segment.step.name === "AskUserQuestion");
}

export default function ChatArea({ entries, runtimeStatus, loading, onFocusAgent, onTaskNoticeClick, agentName, agentAvatarUrl, userName, userAvatarUrl, askUserQuestion }: ChatAreaProps) {
  const containerRef = useStickyScroll<HTMLDivElement>();
  const askUserQuestionDisplays = new Map<
    string,
    | { mode: "pending"; pending: AskUserQuestionPendingState }
    | {
        mode: "answered";
        answered: NonNullable<ReturnType<typeof parseAskUserQuestionAnswerPayload>>;
      }
  >();

  let lastAskAssistantId: string | null = null;
  for (const entry of entries) {
    if (entry.role === "assistant" && hasAskUserQuestionTool(entry as AssistantTurn)) {
      lastAskAssistantId = entry.id;
      continue;
    }
    if (entry.role === "user" && "showing" in entry && entry.showing === false) {
      const answered = entry.ask_user_question_answered ?? parseAskUserQuestionAnswerPayload(entry.content);
      if (answered && lastAskAssistantId) {
        askUserQuestionDisplays.set(lastAskAssistantId, { mode: "answered", answered });
        lastAskAssistantId = null;
      }
    }
  }

  if (askUserQuestion) {
    const pendingAssistant = [...entries]
      .reverse()
      .find((entry): entry is AssistantTurn => entry.role === "assistant" && hasAskUserQuestionTool(entry as AssistantTurn));
    if (pendingAssistant) {
      askUserQuestionDisplays.set(pendingAssistant.id, { mode: "pending", pending: askUserQuestion });
    }
  }

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto py-5 bg-background">
      {loading ? (
        <ChatSkeleton />
      ) : (
        <div className="max-w-3xl mx-auto px-5 space-y-3.5">
          {entries.map((entry) => {
            const isHidden = "showing" in entry && entry.showing === false;
            if (isHidden) return null;
            if (entry.role === "notice") {
              return <NoticeBubble key={entry.id} entry={entry as NoticeMessage} onTaskNoticeClick={onTaskNoticeClick} />;
            }
            if (entry.role === "user") {
              return (
                <div key={entry.id}>
                  <UserBubble entry={entry} userName={userName} avatarUrl={userAvatarUrl} />
                </div>
              );
            }
            const assistantEntry = entry as AssistantTurn;
            const isStreamingThis = assistantEntry.streaming === true;
            return (
              <div key={entry.id}>
                <AssistantBlock
                  entry={assistantEntry}
                  isStreamingThis={isStreamingThis}
                  runtimeStatus={isStreamingThis ? runtimeStatus : null}
                  onFocusAgent={onFocusAgent}
                  agentName={agentName}
                  agentAvatarUrl={agentAvatarUrl}
                  askUserQuestion={askUserQuestionDisplays.get(assistantEntry.id)}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
