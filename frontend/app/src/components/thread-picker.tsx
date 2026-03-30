import { Check, ChevronsUpDown, ExternalLink, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { listThreads, type ThreadSummary } from "@/api";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

export type ThreadPickerScope = "owned" | "visible";

interface ThreadPickerProps {
  scope: ThreadPickerScope;
  value: string;
  threads?: ThreadSummary[];
  onSelect: (thread: ThreadSummary) => void;
}

export function ThreadPicker({ scope, value, threads: initialThreads = [], onSelect }: ThreadPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loadedThreads, setLoadedThreads] = useState<ThreadSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    // @@@thread-picker-load-on-open - keep fetch work behind explicit user action so the editor stays cheap to render.
    listThreads(scope)
      .then((items) => {
        if (cancelled) return;
        setLoadedThreads(items);
      })
      .catch((err) => {
        if (cancelled) return;
        const detail = err instanceof Error ? err.message : "unknown error";
        setError(`加载 thread 失败: ${detail}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, scope]);

  const threads = loadedThreads.length > 0 ? loadedThreads : initialThreads;

  const selectedThread = threads.find((thread) => thread.thread_id === value) ?? null;
  const selectedThreadHref = selectedThread?.member_id
    ? `/threads/${encodeURIComponent(selectedThread.member_id)}/${encodeURIComponent(selectedThread.thread_id)}`
    : null;
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return threads;
    return threads.filter((thread) => {
      const haystack = [
        thread.thread_id,
        thread.entity_name,
        thread.member_name,
        thread.sidebar_label,
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(needle);
    });
  }, [query, threads]);

  return (
      <div className="flex items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="flex flex-1 items-center justify-between gap-3 rounded-xl border border-border bg-card px-3.5 py-2.5 text-left transition-colors hover:border-primary/40"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">
                  {selectedThread ? (selectedThread.entity_name || selectedThread.member_name || value) : (value || "选择 Thread")}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {selectedThread ? [selectedThread.sidebar_label, selectedThread.thread_id].filter(Boolean).join(" · ") : (value ? "已绑定 thread" : "选择一个长期存在的 thread")}
                </div>
              </div>
              <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" sideOffset={10} collisionPadding={16} className="w-[var(--radix-popover-trigger-width)] min-w-[280px] rounded-2xl border-border bg-background/98 p-3 shadow-xl">
            <div className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索 thread..."
                className="w-full bg-transparent text-sm text-foreground outline-none"
              />
            </div>

            <div className="mt-3 max-h-64 space-y-2 overflow-y-auto">
              {loading ? (
                <div className="rounded-xl border border-dashed border-border px-3.5 py-5 text-sm text-muted-foreground">
                  加载中...
                </div>
              ) : error ? (
                <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-3.5 py-5 text-sm text-destructive">
                  {error}
                </div>
              ) : filtered.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border px-3.5 py-5 text-sm text-muted-foreground">
                  {threads.length === 0 ? "没有可选 thread" : "没有匹配的 thread"}
                </div>
              ) : filtered.map((thread) => (
                <button
                  key={thread.thread_id}
                  type="button"
                  onClick={() => {
                    onSelect(thread);
                    setOpen(false);
                    setQuery("");
                  }}
                  className="flex w-full items-start justify-between gap-3 rounded-xl border border-border bg-card/70 px-3.5 py-3 text-left transition-colors hover:border-primary/40 hover:bg-card"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground">{thread.entity_name || thread.member_name || thread.thread_id}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{[thread.sidebar_label, thread.thread_id].filter(Boolean).join(" · ")}</div>
                  </div>
                  {thread.thread_id === value ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> : null}
                </button>
              ))}
            </div>
          </PopoverContent>
        </Popover>
        {selectedThreadHref ? (
          <a
            href={selectedThreadHref}
            className="inline-flex items-center gap-1 rounded-xl border border-border px-3 py-2 text-xs text-primary transition-colors hover:bg-primary/5"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            查看
          </a>
        ) : null}
      </div>
  );
}
