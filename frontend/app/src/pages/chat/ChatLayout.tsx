import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import SplitPaneLayout from "@/components/SplitPaneLayout";
import ConversationList from "./ConversationList";
import { useThreadManager } from "@/hooks/use-thread-manager";

export default function ChatLayout() {
  const params = useParams();
  const hasActiveConversation = Boolean(params.threadId || params.chatId || params.memberId);
  const tm = useThreadManager();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);

  const outletContext = useMemo(
    () => ({ tm, sidebarCollapsed, setSidebarCollapsed, setSessionsOpen }),
    [tm, sidebarCollapsed],
  );

  return (
    <SplitPaneLayout
      sidebar={<ConversationList />}
      hasDetail={hasActiveConversation}
      emptyMessage="选择一个对话开始"
      outletContext={outletContext}
    />
  );
}
