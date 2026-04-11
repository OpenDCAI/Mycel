import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import SplitPaneLayout from "@/components/SplitPaneLayout";
import ConversationList from "./ConversationList";
import { useThreadManager } from "@/hooks/use-thread-manager";
import { useConversationStore } from "@/store/conversation-store";

export default function ChatLayout() {
  const params = useParams();
  const hasActiveConversation = Boolean(params.threadId || params.chatId || params.agentId);
  const tm = useThreadManager();
  const refreshChatList = useConversationStore((s) => s.fetchConversations);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [, setSessionsOpen] = useState(false);

  const outletContext = useMemo(
    () => ({ tm, sidebarCollapsed, setSidebarCollapsed, setSessionsOpen, refreshChatList }),
    [tm, sidebarCollapsed, refreshChatList],
  );

  return (
    <SplitPaneLayout
      sidebar={<ConversationList threads={tm.threads} />}
      hasDetail={hasActiveConversation}
      emptyMessage="选择一个对话开始"
      outletContext={outletContext}
    />
  );
}
