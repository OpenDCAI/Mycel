import { memo } from "react";
import { useParams } from "react-router-dom";
import { FileText } from "lucide-react";
import type { UserMessage } from "../../api";
<<<<<<< HEAD
import MemberAvatar from "../MemberAvatar";
import { formatTime } from "./utils";

interface UserBubbleProps {
  entry?: UserMessage;   // threads path
  content?: string;      // direct content (chat path)
  timestamp?: number;    // direct timestamp (chat path)
  userName?: string;
  avatarUrl?: string;
}

export const UserBubble = memo(function UserBubble(props: UserBubbleProps) {
  const text = props.content ?? props.entry?.content ?? "";
  const ts = props.timestamp ?? props.entry?.timestamp;
=======
import { getWorkspaceDownloadUrl } from "../../api";
import { formatTime } from "./utils";

/** Strip legacy "[User uploaded N file(s) to /workspace/files/: ...]" prefix from message content. */
function stripUploadPrefix(content: string): string {
  return content.replace(/^\[User uploaded \d+ file\(s\) to [^\]]+\]\s*/i, "");
}

export const UserBubble = memo(function UserBubble({ entry }: { entry: UserMessage }) {
  const { threadId } = useParams<{ threadId: string }>();
  const attachments = entry.attachments;
  const displayContent = attachments?.length ? stripUploadPrefix(entry.content) : entry.content;

>>>>>>> da734586 (refactor: architecture cleanup + docker proxy fix)
  return (
    <div className="flex justify-end gap-2 mb-1 animate-fade-in">
      <div className="max-w-[78%]">
        {attachments && attachments.length > 0 && threadId && (
          <div className="mb-1.5 flex flex-wrap gap-1.5 justify-end">
            {attachments.map((filename) => (
              <a
                key={filename}
                href={getWorkspaceDownloadUrl(threadId, filename)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#f0f0f0] hover:bg-[#e8e8e8] rounded-lg text-xs transition-colors cursor-pointer"
              >
                <FileText className="w-3.5 h-3.5 text-[#737373] flex-shrink-0" />
                <span className="text-[#404040] truncate max-w-[180px]">{filename}</span>
              </a>
            ))}
          </div>
        )}
        <div className="rounded-xl rounded-br-sm px-3.5 py-2 bg-[#f5f5f5] border border-[#e5e5e5]">
          <p className="text-[13px] whitespace-pre-wrap leading-[1.55] text-[#171717]">
<<<<<<< HEAD
            {text}
=======
            {displayContent}
>>>>>>> da734586 (refactor: architecture cleanup + docker proxy fix)
          </p>
        </div>
        {ts && (
          <div className="text-[10px] text-right mt-1 pr-1 text-[#d4d4d4]">
            {formatTime(ts)}
          </div>
        )}
      </div>
      <MemberAvatar name={props.userName || "You"} avatarUrl={props.avatarUrl} size="xs" type="human" />
    </div>
  );
});
