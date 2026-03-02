import { MessageSquarePlus, MoreHorizontal, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { ThreadSummary } from "../api";
import { useAppStore } from "../store/app-store";
import { Skeleton } from "./ui/skeleton";

type DateGroup = "今天" | "昨天" | "更早";

function getDateGroup(dateStr?: string): DateGroup {
  if (!dateStr) return "更早";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "更早";
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 86400000);
  if (date >= todayStart) return "今天";
  if (date >= yesterdayStart) return "昨天";
  return "更早";
}

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffMinutes < 1) return "刚刚";
  if (diffMinutes < 60) return `${diffMinutes}分钟前`;
  if (diffHours < 24) return `${diffHours}小时前`;
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 86400000);
  if (date >= yesterdayStart && date < todayStart) return "昨天";
  if (diffDays < 7) return `${diffDays}天前`;
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

interface SidebarProps {
  threads: ThreadSummary[];
  collapsed?: boolean;
  loading?: boolean;
  width?: number;
  onDeleteThread: (threadId: string) => void;
  onSearchClick: () => void;
  onNewChat: () => void;
}

function ThreadSkeleton() {
  return (
    <div className="space-y-0.5">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="px-3 py-2.5 rounded-lg" style={{ animationDelay: `${i * 0.08}s` }}>
          <Skeleton className="h-4 w-[70%] mb-1.5" />
          <Skeleton className="h-3 w-[40%]" />
        </div>
      ))}
    </div>
  );
}

export default function Sidebar({
  threads,
  collapsed = false,
  loading = false,
  width = 272,
  onDeleteThread,
  onSearchClick,
  onNewChat,
}: SidebarProps) {
  const { threadId } = useParams<{ threadId?: string }>();
  const activeThreadId = threadId || null;
  const memberList = useAppStore(s => s.memberList);
  const memberNameMap = new Map(memberList.map(m => [m.id, m.name]));
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  if (collapsed) {
    return (
      <div className="w-14 h-full flex flex-col items-center py-4 bg-card border-r border-border animate-slide-in">
        <button
          onClick={onNewChat}
          className="w-9 h-9 rounded-lg flex items-center justify-center mb-2 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Plus className="w-4.5 h-4.5" />
        </button>
        <button
          className="w-9 h-9 rounded-lg flex items-center justify-center mb-2 text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={onSearchClick}
        >
          <Search className="w-4.5 h-4.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-card border-r border-border animate-slide-in flex-shrink-0" style={{ width }}>
      {/* Header */}
      <div className="px-4 pt-3 pb-1 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">消息</span>
      </div>

      {/* Actions */}
      <div className="px-3 pb-3">
        <button
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground/60 hover:bg-muted hover:text-foreground"
          onClick={onSearchClick}
        >
          <Search className="w-4 h-4" />
          <span>搜索对话...</span>
        </button>
      </div>

      {/* Divider */}
      <div className="h-px mx-3 bg-border" />

      {/* Thread list */}
      <div className="flex-1 min-h-0 px-3 pt-3 flex flex-col">
        <div className="flex items-center justify-between px-2 mb-2 flex-shrink-0">
          <span className="text-[11px] font-medium tracking-wider uppercase text-muted-foreground/60">对话</span>
          <span className="text-[11px] text-muted-foreground/40">{threads.length}</span>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto space-y-0.5 custom-scrollbar">
          {loading ? (
            <ThreadSkeleton />
          ) : (
            <>
              {(() => {
                const sorted = [...threads].sort((a, b) => {
                  const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
                  const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
                  return tb - ta;
                });
                let lastGroup: DateGroup | null = null;
                return sorted.map((thread) => {
                const isActive = activeThreadId === thread.thread_id;
                const group = getDateGroup(thread.updated_at);
                const showGroupLabel = group !== lastGroup;
                lastGroup = group;
                return (
                  <div key={thread.thread_id}>
                    {showGroupLabel && (
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60 px-3 pt-3 pb-1">
                        {group}
                      </div>
                    )}
                  <div className="group/item relative">
                    <Link
                      to={`/chat/${thread.thread_id}`}
                      className={`block w-full text-left px-3 py-2.5 rounded-lg transition-colors ${
                        isActive
                          ? "bg-background border-l-2 border-l-foreground shadow-sm"
                          : "border-l-2 border-l-transparent hover:bg-muted"
                      }`}
                    >
                      <div className={`flex items-center gap-1.5 ${isActive ? "text-foreground font-medium" : "text-foreground"}`}>
                        {thread.running && (
                          <span className="w-3 h-3 rounded-full border-2 border-muted-foreground border-t-foreground animate-spin flex-shrink-0" />
                        )}
                        <span className="text-sm font-medium truncate">
                          {thread.agent ? (memberNameMap.get(thread.agent) || thread.agent) : "Leon"}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 mt-0.5">
                        <span className="text-[11px] text-muted-foreground/60 truncate flex-1 min-w-0">
                          {thread.preview || thread.thread_id.slice(0, 14)}
                        </span>
                        {thread.updated_at && (
                          <span className="text-[10px] text-muted-foreground/40 flex-shrink-0">
                            {formatRelativeTime(thread.updated_at)}
                          </span>
                        )}
                      </div>
                    </Link>
                    <div className={`absolute right-2 top-2.5 ${confirmDelete === thread.thread_id ? "flex" : "hidden group-hover/item:flex"} items-center gap-0.5`}>
                      {confirmDelete === thread.thread_id ? (
                        <>
                          <button
                            className="w-6 h-6 rounded flex items-center justify-center text-destructive bg-destructive/10 hover:bg-destructive/20"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setConfirmDelete(null);
                              onDeleteThread(thread.thread_id);
                            }}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground/60 hover:bg-muted hover:text-foreground text-xs"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setConfirmDelete(null);
                            }}
                          >
                            ✕
                          </button>
                        </>
                      ) : (
                        <button
                          className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground/60 hover:bg-muted hover:text-foreground"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setConfirmDelete(thread.thread_id);
                          }}
                        >
                          <MoreHorizontal className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                  </div>
                );
              });
              })()}
              {threads.length === 0 && (
                <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
                  <div className="w-10 h-10 rounded-xl bg-muted flex items-center justify-center mb-3">
                    <MessageSquarePlus className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <p className="text-xs font-medium text-foreground mb-1">暂无对话</p>
                  <p className="text-[11px] text-muted-foreground/60 mb-3">发起一个会话，开始与 Agent 协作</p>
                  <button
                    onClick={onNewChat}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    发起会话
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

    </div>
  );
}
