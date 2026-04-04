import { useState } from "react";
import { Link, Outlet, useParams } from "react-router-dom";
import { DragHandle } from "../components/DragHandle";
import NewChatDialog from "../components/NewChatDialog";
import NewThreadModal from "../components/NewThreadModal";
import SandboxSessionsModal from "../components/SandboxSessionsModal";
import SearchModal from "../components/SearchModal";
import Sidebar from "../components/Sidebar";
import type { ThreadSummary } from "../api";
import { useIsMobile } from "../hooks/use-mobile";
import { useResizableX } from "../hooks/use-resizable-x";
import { useThreadManager } from "../hooks/use-thread-manager";
import MemberAvatar from "../components/MemberAvatar";
import { Plus, Trash2 } from "lucide-react";

function requireThreadMemberId(thread: { thread_id: string; member_id?: string }): string {
  // @@@thread-member-id-required - mobile thread navigation must use stable member IDs, not mutable display names.
  if (!thread.member_id) {
    throw new Error(`Thread ${thread.thread_id} missing member_id`);
  }
  return thread.member_id;
}

export default function AppLayout() {
  const tm = useThreadManager();
  const {
    threads, sandboxTypes, loading,
    refreshThreads, handleCreateThread, handleDeleteThread,
  } = tm;

  const isMobile = useIsMobile();
  const { threadId } = useParams<{ memberId?: string; threadId?: string }>();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [newThreadOpen, setNewThreadOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [newChatOpen, setNewChatOpen] = useState(false);

  const sidebarResize = useResizableX(272, 200, 420);

  if (isMobile) {
    if (!threadId) {
      return (
        <MobileThreadList
          threads={threads}
          loading={loading}
          onNewChat={() => setNewChatOpen(true)}
          onDeleteThread={(id) => void handleDeleteThread(id)}
          newChatOpen={newChatOpen}
          setNewChatOpen={setNewChatOpen}
        />
      );
    }
    return (
      <div className="h-full w-full bg-background flex flex-col overflow-hidden">
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <Outlet context={{ tm, sidebarCollapsed, setSidebarCollapsed, setSessionsOpen }} />
        </div>
        <NewChatDialog open={newChatOpen} onOpenChange={setNewChatOpen} />
      </div>
    );
  }
  return (
    <div className="h-full w-full bg-background flex overflow-hidden">
      <Sidebar
        threads={threads}
        collapsed={sidebarCollapsed}
        loading={loading}
        width={sidebarResize.width}
        onDeleteThread={(id) => void handleDeleteThread(id)}
        onSearchClick={() => setSearchOpen(true)}
        onNewChat={() => setNewChatOpen(true)}
      />
      {!sidebarCollapsed && <DragHandle onMouseDown={sidebarResize.onMouseDown} />}

      <div className="flex-1 flex flex-col min-w-0">
        <Outlet context={{ tm, sidebarCollapsed, setSidebarCollapsed, setSessionsOpen }} />
      </div>

      <NewThreadModal
        open={newThreadOpen}
        sandboxTypes={sandboxTypes}
        onClose={() => setNewThreadOpen(false)}
        onCreate={(sandbox, cwd) => {
          setNewThreadOpen(false);
          void handleCreateThread(sandbox, cwd);
        }}
      />

      <SearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        threads={threads}
        onSelectThread={() => {}}
      />

      <SandboxSessionsModal
        isOpen={sessionsOpen}
        onClose={() => setSessionsOpen(false)}
        onSessionMutated={() => {
          void refreshThreads();
        }}
      />

      <NewChatDialog open={newChatOpen} onOpenChange={setNewChatOpen} />
    </div>
  );
}

function MobileThreadList({ threads, loading, onNewChat, onDeleteThread, newChatOpen, setNewChatOpen }: {
  threads: ThreadSummary[];
  loading: boolean;
  onNewChat: () => void;
  onDeleteThread: (id: string) => void;
  newChatOpen: boolean;
  setNewChatOpen: (v: boolean) => void;
}) {
  return (
    <div className="h-full w-full bg-background flex flex-col overflow-hidden">
      <div className="h-14 flex items-center justify-between px-4 border-b border-border shrink-0">
        <h2 className="text-sm font-semibold text-foreground">消息</h2>
        <button onClick={onNewChat} className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted">
          <Plus className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <p className="text-sm text-muted-foreground text-center py-8">加载中...</p>
        ) : threads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 px-4">
            <p className="text-sm text-muted-foreground mb-3">暂无会话</p>
            <button onClick={onNewChat} className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm">发起会话</button>
          </div>
        ) : (
          threads.map(t => {
            const memberId = requireThreadMemberId(t);
            const entityName = t.entity_name || t.member_name || "Agent";
            const subtitle = t.is_main ? "主线对话" : (t.sidebar_label || "分支对话");
            return (
              <div key={t.thread_id} className="flex items-center border-b border-border">
                <Link to={`/threads/${encodeURIComponent(memberId)}/${t.thread_id}`} className="flex items-center gap-3 px-4 py-3 flex-1 min-w-0 hover:bg-muted/50 transition-colors duration-fast">
                  <MemberAvatar name={entityName} avatarUrl={t.avatar_url} type="mycel_agent" size="md" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground truncate">{entityName}</p>
                    <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
                  </div>
                </Link>
                <button
                  onClick={() => onDeleteThread(t.thread_id)}
                  className="w-8 h-8 flex items-center justify-center text-muted-foreground/40 hover:text-destructive transition-colors duration-fast shrink-0 mr-1"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>
      <NewChatDialog open={newChatOpen} onOpenChange={setNewChatOpen} />
    </div>
  );
}
