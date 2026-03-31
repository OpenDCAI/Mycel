import { memo } from "react";
import { useParams } from "react-router-dom";
import { FileText } from "lucide-react";
import type { UserMessage } from "../../api";
import { getSandboxDownloadUrl } from "../../api";
import MemberAvatar from "../MemberAvatar";
import { formatTime } from "./utils";

/** Strip "[User uploaded N file(s)...]" prefix from message content. */
function stripUploadPrefix(content: string): string {
  return content.replace(/^\[User uploaded \d+ file\(s\)[^\]]*\]\s*/i, "");
}

interface UserBubbleProps {
  entry?: UserMessage;   // threads path
  content?: string;      // direct content (chat path)
  timestamp?: number;    // direct timestamp (chat path)
  userName?: string;
  avatarUrl?: string;
}

export const UserBubble = memo(function UserBubble(props: UserBubbleProps) {
  const { threadId } = useParams<{ threadId: string }>();
  const attachments = props.entry?.attachments;
  const rawText = props.content ?? props.entry?.content ?? "";
  const displayContent = stripUploadPrefix(rawText);
  const ts = props.timestamp ?? props.entry?.timestamp;

  return (
    <div className="flex justify-end gap-2 mb-1 animate-fade-in">
      <div className="max-w-[78%]">
        {attachments && attachments.length > 0 && threadId && (
          <div className="mb-1.5 flex flex-wrap gap-1.5 justify-end">
            {attachments.map((filename) => (
              <a
                key={filename}
                href={getSandboxDownloadUrl(threadId, filename)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#f0f0f0] hover:bg-[#e8e8e8] rounded-lg text-xs transition-colors duration-fast cursor-pointer"
              >
                <FileText className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                <span className="text-foreground-secondary truncate max-w-[180px]">{filename}</span>
              </a>
            ))}
          </div>
        )}
        <div className="rounded-xl rounded-br-sm px-3.5 py-2 bg-muted border border-border">
          <p className="text-sm whitespace-pre-wrap leading-[1.55] text-foreground">
            {displayContent}
          </p>
        </div>
        {ts && (
          <div className="text-2xs text-right mt-1 pr-1 text-muted-foreground/30">
            {formatTime(ts)}
          </div>
        )}
      </div>
      <MemberAvatar name={props.userName || "You"} avatarUrl={props.avatarUrl} size="xs" type="human" />
    </div>
  );
});
