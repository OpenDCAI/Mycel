import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, Outlet, useParams } from "react-router-dom";
import { DragHandle } from "../components/DragHandle";
import NewChatDialog from "../components/NewChatDialog";
import NewThreadModal from "../components/NewThreadModal";
import SandboxSessionsModal from "../components/SandboxSessionsModal";
import SearchModal from "../components/SearchModal";
import Sidebar from "../components/Sidebar";
import { useIsMobile } from "../hooks/use-mobile";
import { useResizableX } from "../hooks/use-resizable-x";
import { useThreadManager } from "../hooks/use-thread-manager";
import { useAppStore } from "../store/app-store";
import { useAuthStore } from "../store/auth-store";
import { listConversations, deleteConversation, type ConversationSummary } from "../api/conversations";
import type { ThreadSummary } from "../api";
import { Plus, Trash2 } from "lucide-react";

export default function AppLayout() {
  const tm = useThreadManager();
  const {
    sandboxTypes, loading: threadLoading,
    refreshThreads, handleCreateThread, handleDeleteThread,
  } = tm;
  const fetchMembers = useAppStore(s => s.fetchMembers);
  useEffect(() => { void fetchMembers(); }, [fetchMembers]);

  // @@@conversation-sidebar - fetch conversations for sidebar display
  const authAgent = useAuthStore(s => s.agent);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [convLoading, setConvLoading] = useState(true);

  const refreshConversations = useCallback(async () => {
    try {
      const convs = await listConversations();
      setConversations(convs);
    } catch (err) {
      console.error("[AppLayout] Failed to fetch conversations:", err);
    }
  }, []);

  useEffect(() => {
    refreshConversations().finally(() => setConvLoading(false));
  }, [refreshConversations]);

  const handleDeleteConversation = useCallback(async (conversationId: string) => {
    try {
      await deleteConversation(conversationId);
      await refreshConversations();
    } catch (err) {
      console.error("[AppLayout] Failed to delete conversation:", err);
    }
  }, [refreshConversations]);

  // @@@conv-as-route-key - each conversation maps to its ACTUAL agent, not the user's own agent.
  const sidebarThreads: ThreadSummary[] = useMemo(() =>
    conversations.map(conv => ({
      thread_id: conv.id,
      preview: conv.title,
      updated_at: new Date(conv.created_at * 1000).toISOString(),
      agent: conv.agent_name || "Leon",
      running: false,
    })),
    [conversations],
  );

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
          threads={sidebarThreads}
          loading={convLoading}
          onNewChat={() => setNewChatOpen(true)}
          onDeleteThread={(id) => void handleDeleteThread(id)}
          newChatOpen={newChatOpen}
          setNewChatOpen={setNewChatOpen}
          onConversationCreated={refreshConversations}
        />
      );
    }
    return (
      <div className="h-full w-full bg-background flex flex-col overflow-hidden">
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <Outlet context={{ tm, conversations, refreshConversations, sidebarCollapsed, setSidebarCollapsed, setSessionsOpen }} />
        </div>
        <NewChatDialog open={newChatOpen} onOpenChange={setNewChatOpen} onConversationCreated={refreshConversations} />
      </div>
    );
  }
  return (
    <div className="h-full w-full bg-background flex overflow-hidden">
      <Sidebar
        threads={sidebarThreads}
        collapsed={sidebarCollapsed}
        loading={convLoading}
        width={sidebarResize.width}
        onDeleteThread={(id) => void handleDeleteConversation(id)}
        onSearchClick={() => setSearchOpen(true)}
        onNewChat={() => setNewChatOpen(true)}
      />
      {!sidebarCollapsed && <DragHandle onMouseDown={sidebarResize.onMouseDown} />}

      <div className="flex-1 flex flex-col min-w-0">
        <Outlet context={{ tm, conversations, refreshConversations, sidebarCollapsed, setSidebarCollapsed, setSessionsOpen }} />
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
        threads={sidebarThreads}
        onSelectThread={() => {}}
      />

      <SandboxSessionsModal
        isOpen={sessionsOpen}
        onClose={() => setSessionsOpen(false)}
        onSessionMutated={() => {
          void refreshThreads();
        }}
      />

      <NewChatDialog open={newChatOpen} onOpenChange={setNewChatOpen} onConversationCreated={refreshConversations} />
    </div>
  );
}

function MobileThreadList({ threads, loading, onNewChat, onDeleteThread, newChatOpen, setNewChatOpen, onConversationCreated }: {
  threads: any[];
  loading: boolean;
  onNewChat: () => void;
  onDeleteThread: (id: string) => void;
  newChatOpen: boolean;
  setNewChatOpen: (v: boolean) => void;
  onConversationCreated: () => Promise<void>;
}) {
  const memberList = useAppStore(s => s.memberList);
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
            const member = memberList.find((m: any) => m.id === t.agent);
            const memberName = member?.name || t.agent || "Leon";
            const preview = t.preview || "新会话";
            return (
              <div key={t.thread_id} className="flex items-center border-b border-border">
                <Link to={`/chat/${t.thread_id}`} className="flex items-center gap-3 px-4 py-3 flex-1 min-w-0 hover:bg-muted/50 transition-colors">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <span className="text-xs font-bold text-primary">{memberName.slice(0, 1)}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground truncate">{memberName}</p>
                    <p className="text-xs text-muted-foreground truncate">{preview}</p>
                  </div>
                </Link>
                <button
                  onClick={() => onDeleteThread(t.thread_id)}
                  className="w-8 h-8 flex items-center justify-center text-muted-foreground/40 hover:text-destructive transition-colors shrink-0 mr-1"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>
      <NewChatDialog open={newChatOpen} onOpenChange={setNewChatOpen} onConversationCreated={onConversationCreated} />
    </div>
  );
}
