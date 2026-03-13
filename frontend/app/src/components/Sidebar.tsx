import { Check, ChevronRight, MoreHorizontal, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { ThreadSummary } from "../api";
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

function ThreadItem({
  thread,
  isActive,
  label,
  to,
  isSelectMode,
  isSelected,
  onToggleSelect,
  confirmDelete,
  setConfirmDelete,
  onDeleteThread,
}: {
  thread: ThreadSummary;
  isActive: boolean;
  label: string;
  to: string;
  isSelectMode: boolean;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  confirmDelete: string | null;
  setConfirmDelete: (id: string | null) => void;
  onDeleteThread: (id: string) => void;
}) {
  return (
    <div className={`group/item flex items-center rounded-lg transition-colors ${
      isSelected ? "bg-primary/10" : isActive ? "bg-background shadow-sm" : "hover:bg-muted"
    }`}>
      {/* Left gutter: fixed w-7, holds active indicator OR checkbox — text never moves */}
      <div className="relative w-7 flex-shrink-0 self-stretch flex items-center justify-center">
        {/* Active indicator line */}
        {isActive && !isSelected && (
          <div className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full bg-foreground" />
        )}
        {isSelected && (
          <div className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full bg-primary" />
        )}
        {/* Checkbox — only visible in select mode */}
        {isSelectMode && (
          <button
            className={`w-4 h-4 rounded border-[1.5px] flex items-center justify-center transition-colors ${
              isSelected ? "bg-primary border-primary" : "border-muted-foreground/40 bg-card"
            }`}
            onClick={(e) => { e.stopPropagation(); onToggleSelect(thread.thread_id); }}
          >
            {isSelected && <Check className="w-2.5 h-2.5 text-primary-foreground" />}
          </button>
        )}
      </div>

      {/* Text content */}
      <Link
        to={isSelectMode ? "#" : to}
        onClick={(e) => { if (isSelectMode) { e.preventDefault(); onToggleSelect(thread.thread_id); } }}
        className="flex-1 min-w-0 py-2.5 pr-2"
      >
        <div className={`flex items-center gap-1.5 ${isActive ? "text-foreground font-medium" : "text-foreground"}`}>
          {thread.running && !isSelectMode && (
            <span className="w-3 h-3 rounded-full border-2 border-muted-foreground border-t-foreground animate-spin flex-shrink-0" />
          )}
          <span className="text-sm font-medium truncate">{label}</span>
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

      {/* Single-item delete — hidden in select mode */}
      {!isSelectMode && (
        <div className={`${confirmDelete === thread.thread_id ? "flex" : "hidden group-hover/item:flex"} items-center gap-0.5 pr-1.5`}>
          {confirmDelete === thread.thread_id ? (
            <>
              <button
                className="w-6 h-6 rounded flex items-center justify-center text-destructive bg-destructive/10 hover:bg-destructive/20"
                onClick={(e) => { e.stopPropagation(); setConfirmDelete(null); onDeleteThread(thread.thread_id); }}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
              <button
                className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground/60 hover:bg-muted hover:text-foreground text-xs"
                onClick={(e) => { e.stopPropagation(); setConfirmDelete(null); }}
              >
                ✕
              </button>
            </>
          ) : (
            <button
              className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground/60 hover:bg-muted hover:text-foreground"
              onClick={(e) => { e.stopPropagation(); setConfirmDelete(thread.thread_id); }}
            >
              <MoreHorizontal className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      )}
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
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [expandedMembers, setExpandedMembers] = useState<Set<string>>(new Set());
  const hasInitialized = useRef(false);
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const onToggleSelect = (threadId: string) => {
    if (!isSelectMode) setIsSelectMode(true);
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(threadId)) next.delete(threadId);
      else next.add(threadId);
      return next;
    });
  };

  const exitSelectMode = () => { setIsSelectMode(false); setSelectedIds(new Set()); };

  const isAllSelected = threads.length > 0 && threads.every(t => selectedIds.has(t.thread_id));

  const handleSelectAll = () => {
    setSelectedIds(isAllSelected ? new Set() : new Set(threads.map(t => t.thread_id)));
  };

  const handleBulkDelete = () => {
    selectedIds.forEach(id => onDeleteThread(id));
    exitSelectMode();
  };

  useEffect(() => {
    if (!isSelectMode) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") exitSelectMode(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isSelectMode]);

  // Group threads by member (agent_name from conversations)
  const groups = useMemo(() => {
    const map = new Map<string, { memberName: string; threads: ThreadSummary[]; latestAt: number }>();

    // Build groups from actual threads only — no seeding from memberList
    for (const thread of threads) {
      const key = thread.agent || "Leon";
      if (!map.has(key)) map.set(key, { memberName: key, threads: [], latestAt: 0 });
      const g = map.get(key)!;
      const at = thread.updated_at ? new Date(thread.updated_at).getTime() : 0;
      g.threads.push(thread);
      g.latestAt = Math.max(g.latestAt, at);
    }

    return [...map.entries()]
      .map(([memberId, g]) => ({ memberId, ...g }))
      .sort((a, b) => b.latestAt - a.latestAt)
      .map(g => ({
        ...g,
        threads: [...g.threads].sort((a, b) => {
          const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
          const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
          return tb - ta;
        }),
      }));
  }, [threads]);

  // Auto-expand the most recently active member on first load
  useEffect(() => {
    if (groups.length > 0 && !hasInitialized.current) {
      hasInitialized.current = true;
      setExpandedMembers(new Set([groups[0].memberId]));
    }
  }, [groups]);

  const toggleMember = (memberId: string) => {
    setExpandedMembers(prev => {
      const next = new Set(prev);
      if (next.has(memberId)) next.delete(memberId);
      else next.add(memberId);
      return next;
    });
  };

  // ── Collapsed (narrow) mode ──────────────────────────────────────────────
  if (collapsed) {
    return (
      <div className="w-14 h-full flex flex-col items-center py-3 bg-card border-r border-border animate-slide-in overflow-hidden flex-shrink-0">
        <button onClick={onNewChat} className="w-9 h-9 rounded-lg flex items-center justify-center mb-1 text-muted-foreground hover:bg-muted hover:text-foreground">
          <Plus className="w-4 h-4" />
        </button>
        <button onClick={onSearchClick} className="w-9 h-9 rounded-lg flex items-center justify-center mb-2 text-muted-foreground hover:bg-muted hover:text-foreground">
          <Search className="w-4 h-4" />
        </button>

        <div className="w-8 h-px bg-border mb-2" />

        <div className="flex-1 min-h-0 overflow-y-auto w-full flex flex-col items-center gap-1 px-2 py-1 custom-scrollbar">
          {groups.map((group) => {
            const isActive = group.threads.some(t => t.thread_id === activeThreadId);
            const isRunning = group.threads.some(t => t.running);
            const initial = group.memberName.slice(0, 1).toUpperCase();
            const latestThread = group.threads[0];
            return (
              <div key={group.memberId} className="relative group/item w-full flex justify-center">
                {isActive && (
                  <div className="absolute -left-[4px] top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-primary" />
                )}
                <Link
                  to={`/chat/${group.memberId}`}
                  title={group.memberName}
                  className={`w-9 h-9 rounded-xl flex items-center justify-center text-xs font-semibold transition-colors ${
                    isActive ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-primary/15 hover:text-primary"
                  }`}
                >
                  {isRunning
                    ? <span className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
                    : initial}
                </Link>
                <div className="absolute left-[52px] top-1/2 -translate-y-1/2 px-2 py-1 bg-foreground text-background text-xs rounded opacity-0 group-hover/item:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50 max-w-[200px] truncate">
                  {group.memberName}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // ── Expanded mode ────────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col bg-card border-r border-border animate-slide-in flex-shrink-0" style={{ width }}>
      {/* Header */}
      <div className="px-4 pt-3 pb-1 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">消息</span>
      </div>

      {/* Search */}
      <div className="px-3 pb-3">
        <button
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground/60 hover:bg-muted hover:text-foreground"
          onClick={onSearchClick}
        >
          <Search className="w-4 h-4" />
          <span>搜索对话...</span>
        </button>
      </div>

      <div className="h-px mx-3 bg-border" />

      {/* Thread list */}
      <div className="flex-1 min-h-0 px-3 pt-3 flex flex-col">
        <div className="flex items-center justify-between px-2 mb-2 flex-shrink-0">
          <span className="text-[11px] font-medium tracking-wider uppercase text-muted-foreground/60">对话</span>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground/40">{threads.length}</span>
            {!isSelectMode && (
              <button
                onClick={() => setIsSelectMode(true)}
                className="text-[11px] text-muted-foreground/50 hover:text-foreground transition-colors px-1"
              >
                管理
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto space-y-0.5 custom-scrollbar">
          {loading ? (
            <ThreadSkeleton />
          ) : (
            groups.map((group) => {
              const isExpanded = expandedMembers.has(group.memberId);
              const initial = group.memberName.slice(0, 1).toUpperCase();
              const urlId = group.memberId === "Leon" ? "leon" : group.memberId;
              return (
                <div key={group.memberId} className="mb-1">
                  {/* Group header: chevron toggles expand, avatar+name navigates to new chat */}
                  <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-muted">
                    <button
                      onClick={() => toggleMember(group.memberId)}
                      className="p-0.5 rounded text-muted-foreground/50 hover:bg-muted-foreground/20 hover:text-muted-foreground flex-shrink-0"
                    >
                      <ChevronRight className={`w-3.5 h-3.5 transition-transform ${isExpanded ? "rotate-90" : ""}`} />
                    </button>
                    <Link
                      to={`/chat/${urlId}`}
                      className="flex items-center gap-2 flex-1 min-w-0"
                    >
                      <div className="w-6 h-6 rounded-lg bg-primary/10 flex items-center justify-center text-[11px] font-semibold text-primary flex-shrink-0">
                        {initial}
                      </div>
                      <span className="text-xs font-medium text-foreground flex-1 truncate">{group.memberName}</span>
                    </Link>
                    <span className="text-[10px] text-muted-foreground/40 flex-shrink-0">{group.threads.length || ""}</span>
                  </div>
                  {isExpanded && (
                    <div className="mt-0.5 ml-3 space-y-0.5">
                      {group.threads.length === 0 ? (
                        <Link
                          to={`/chat/${urlId}`}
                          className="block px-3 py-2 text-[11px] text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                        >
                          + 发起新对话
                        </Link>
                      ) : (
                        group.threads.map((thread) => (
                          <ThreadItem
                            key={thread.thread_id}
                            thread={thread}
                            isActive={activeThreadId === thread.thread_id}
                            label={thread.preview || thread.thread_id.slice(0, 14)}
                            to={`/chat/${urlId}/${thread.thread_id}`}
                            isSelectMode={isSelectMode}
                            isSelected={selectedIds.has(thread.thread_id)}
                            onToggleSelect={onToggleSelect}
                            confirmDelete={confirmDelete}
                            setConfirmDelete={setConfirmDelete}
                            onDeleteThread={onDeleteThread}
                          />
                        ))
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Bulk action bar */}
      {isSelectMode && (
        <div className="px-3 py-2.5 border-t border-border flex items-center gap-2 flex-shrink-0">
          <button
            onClick={handleSelectAll}
            className="text-xs text-muted-foreground/70 hover:text-foreground transition-colors"
          >
            {isAllSelected ? "取消全选" : "全选"}
          </button>
          <span className="text-xs text-muted-foreground/40">·</span>
          <span className="text-xs text-muted-foreground flex-1">已选 {selectedIds.size} 条</span>
          <button
            onClick={handleBulkDelete}
            disabled={selectedIds.size === 0}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-destructive/10 text-destructive hover:bg-destructive/20 disabled:opacity-40 text-xs font-medium transition-colors"
          >
            <Trash2 className="w-3 h-3" />
            删除
          </button>
          <button
            onClick={exitSelectMode}
            className="px-2.5 py-1.5 rounded-lg text-xs text-muted-foreground hover:bg-muted transition-colors"
          >
            取消
          </button>
        </div>
      )}
    </div>
  );
}
