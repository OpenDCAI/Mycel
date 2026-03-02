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
              value={`${thread.thread_id} ${thread.sandbox ?? "local"} ${thread.preview ?? ""}`}
              onSelect={() => {
                onSelectThread(thread.thread_id);
                onClose();
              }}
            >
              <div className="flex flex-col gap-0.5">
                <span className="text-sm">{thread.preview || thread.thread_id}</span>
                <span className="text-xs text-muted-foreground">{thread.sandbox ?? "local"}</span>
              </div>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
