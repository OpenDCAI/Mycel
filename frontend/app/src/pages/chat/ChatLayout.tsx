import { useParams } from "react-router-dom";
import SplitPaneLayout from "@/components/SplitPaneLayout";
import ConversationList from "./ConversationList";

export default function ChatLayout() {
  const params = useParams();
  const hasActiveConversation = Boolean(params.threadId || params.chatId || params.memberId);

  return (
    <SplitPaneLayout
      sidebar={<ConversationList />}
      hasDetail={hasActiveConversation}
      emptyMessage="选择一个对话开始"
    />
  );
}
