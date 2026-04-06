import type { ThreadSummary } from "../api";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "./ui/command";

interface SearchModalProps {
  isOpen: boolean;
  threads: ThreadSummary[];
  onClose: () => void;
  onSelectThread: (threadId: string) => void;
}

export default function SearchModal({ isOpen, threads, onClose, onSelectThread }: SearchModalProps) {
  return (
    <CommandDialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title="搜索对话"
      description="搜索对话或运行环境"
      showCloseButton={false}
    >
      <CommandInput placeholder="搜索对话或运行环境..." />
      <CommandList className="max-h-[440px]">
        <CommandEmpty>未找到匹配的对话</CommandEmpty>
        <CommandGroup>
          {threads.map((thread) => (
            <CommandItem
              key={thread.thread_id}
              value={`${thread.thread_id} ${thread.sandbox ?? "local"} ${thread.member_name ?? ""} ${thread.sidebar_label ?? ""}`}
              onSelect={() => {
                onSelectThread(thread.thread_id);
                onClose();
              }}
            >
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="text-sm truncate">{thread.member_name || thread.thread_id}</span>
                <span className="text-xs text-muted-foreground flex gap-2">
                  <span>{thread.sandbox ?? "local"}</span>
                  {thread.updated_at && (
                    <span>{new Date(thread.updated_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                  )}
                </span>
              </div>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
