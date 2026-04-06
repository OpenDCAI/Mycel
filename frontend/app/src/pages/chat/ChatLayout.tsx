import { Outlet, useParams } from "react-router-dom";
import { useIsMobile } from "@/hooks/use-mobile";
import ConversationList from "./ConversationList";

export default function ChatLayout() {
  const isMobile = useIsMobile();
  const params = useParams();
  const hasActiveConversation = Boolean(params.threadId || params.chatId || params.memberId);

  if (isMobile) {
    // Mobile: show list or conversation, not both
    if (hasActiveConversation) {
      return (
        <div className="h-full w-full">
          <Outlet />
        </div>
      );
    }
    return (
      <div className="h-full w-full">
        <ConversationList />
      </div>
    );
  }

  // Desktop: side-by-side
  return (
    <div className="h-full w-full flex overflow-hidden">
      <div className="w-72 shrink-0 h-full">
        <ConversationList />
      </div>
      <div className="flex-1 min-w-0">
        {hasActiveConversation ? (
          <Outlet />
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-sm text-muted-foreground">选择一个对话开始</p>
          </div>
        )}
      </div>
    </div>
  );
}
