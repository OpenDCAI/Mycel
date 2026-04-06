import { memo } from "react";
import MemberAvatar from "../MemberAvatar";
import MarkdownContent from "../MarkdownContent";
import { formatTime } from "./utils";

interface ChatBubbleProps {
  content: string;
  senderName: string;
  avatarUrl?: string;
  memberType?: string;
  timestamp?: number;
  showName?: boolean;
}

export const ChatBubble = memo(function ChatBubble({
  content,
  senderName,
  avatarUrl,
  memberType,
  timestamp,
  showName = true,
}: ChatBubbleProps) {
  return (
    <div className="flex gap-2.5 mb-1 animate-fade-in">
      <MemberAvatar name={senderName} avatarUrl={avatarUrl} type={memberType} size="xs" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {showName && <span className="text-sm font-medium text-foreground">{senderName}</span>}
          {timestamp && <span className="text-2xs text-muted-foreground/30">{formatTime(timestamp)}</span>}
        </div>
        <MarkdownContent content={content} />
      </div>
    </div>
  );
});
