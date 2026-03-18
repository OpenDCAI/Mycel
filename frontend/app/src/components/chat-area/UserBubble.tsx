import { memo } from "react";
import type { UserMessage } from "../../api";
import MemberAvatar from "../MemberAvatar";
import { formatTime } from "./utils";

interface UserBubbleProps {
  entry?: UserMessage;   // threads path
  content?: string;      // direct content (chat path)
  timestamp?: number;    // direct timestamp (chat path)
  userName?: string;
}

export const UserBubble = memo(function UserBubble(props: UserBubbleProps) {
  const text = props.content ?? props.entry?.content ?? "";
  const ts = props.timestamp ?? props.entry?.timestamp;
  return (
    <div className="flex justify-end gap-2 mb-1 animate-fade-in">
      <div className="max-w-[78%]">
        <div className="rounded-xl rounded-br-sm px-3.5 py-2 bg-[#f5f5f5] border border-[#e5e5e5]">
          <p className="text-[13px] whitespace-pre-wrap leading-[1.55] text-[#171717]">
            {text}
          </p>
        </div>
        {ts && (
          <div className="text-[10px] text-right mt-1 pr-1 text-[#d4d4d4]">
            {formatTime(ts)}
          </div>
        )}
      </div>
      <MemberAvatar name={props.userName || "You"} size="xs" type="human" />
    </div>
  );
});
