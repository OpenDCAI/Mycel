import { useCallback, useEffect, useState } from "react";
import { useParams, useOutletContext, useLocation } from "react-router-dom";
import ChatArea, { type ViewMode } from "../components/ChatArea";
import ConversationView from "../components/chat-area/ConversationView";
import type { AssistantTurn } from "../api";
import { Eye, MessageSquareText } from "lucide-react";
import ComputerPanel from "../components/ComputerPanel";
import { DragHandle } from "../components/DragHandle";
import Header from "../components/Header";
import InputBox from "../components/InputBox";
import TaskProgress from "../components/TaskProgress";
import TokenStats from "../components/TokenStats";
import { useAppActions } from "../hooks/use-app-actions";
import { useBackgroundTasks } from "../hooks/use-background-tasks";
import { BackgroundSessionsIndicator } from "../components/chat-area/BackgroundSessionsIndicator";
import { useResizableX } from "../hooks/use-resizable-x";
import { useSandboxManager } from "../hooks/use-sandbox-manager";
import { useStreamHandler } from "../hooks/use-stream-handler";
import { useThreadData } from "../hooks/use-thread-data";
import type { ThreadManagerState, ThreadManagerActions } from "../hooks/use-thread-manager";
import type { ConversationSummary } from "../api/conversations";
import { useAuthStore } from "../store/auth-store";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
  conversations: ConversationSummary[];
  refreshConversations: () => Promise<void>;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  setSessionsOpen: (value: boolean) => void;
}

/** Thin wrapper: key={threadId} forces remount → all hook state resets naturally. */
export default function ChatPage() {
  const { threadId } = useParams<{ memberId: string; threadId: string }>();
  if (!threadId) return null;
  return <ChatPageInner key={threadId} threadId={threadId} />;
}

function ChatPageInner({ threadId }: { threadId: string }) {
  const location = useLocation();
  const { tm, conversations, setSidebarCollapsed } = useOutletContext<OutletContext>();

  // @@@conv-routing - threadId from URL is now a conversation ID.
  // Look up conversation → derive brain thread ID for internal use.
  const conversation = conversations?.find(c => c.id === threadId);
  const brainThreadId = conversation ? `brain-${conversation.agent_member_id}` : threadId;

  // @@@own-agent-check - only the agent's owner sees the brain thread (full view).
  // For other people's agents, always show contact view.
  const authAgent = useAuthStore(s => s.agent);
  const isOwnAgent = conversation ? conversation.agent_member_id === authAgent?.id : false;

  const [currentModel, setCurrentModel] = useState<string>("");
  // @@@view-default — conversation view is primary for everyone.
  // Toggle to "owner" (brain thread) available only for own agent.
  // key={threadId} on parent forces remount, so default applies fresh each time.
  const [viewMode, setViewMode] = useState<ViewMode>("contact");

  const state = location.state as { selectedModel?: string; runStarted?: boolean; message?: string } | null;

  const runStarted = !!state?.runStarted;

  const [initialEntries] = useState(() => {
    if (!runStarted || !state?.message) return undefined;
    const now = Date.now();
    return [
      { id: `user-${now}`, role: "user" as const, content: state.message, timestamp: now },
      { id: `assistant-${now + 1}`, role: "assistant" as const, segments: [], streaming: true, timestamp: now + 1 } as AssistantTurn,
    ];
  });

  useEffect(() => {
    if (state?.selectedModel) {
      setCurrentModel(state.selectedModel);
      void fetch("/api/settings/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: state.selectedModel, thread_id: brainThreadId }),
      });
    } else {
      fetch(`/api/threads/${brainThreadId}/runtime`)
        .then((r) => r.json())
        .then((d) => {
          if (d.model) {
            setCurrentModel(d.model);
          } else {
            return fetch("/api/settings")
              .then((r) => r.json())
              .then((d) => setCurrentModel(d.default_model || "leon:large"));
          }
        })
        .catch(() => setCurrentModel("leon:large"));
    }
  }, [state?.selectedModel, brainThreadId]);

  const { entries, activeSandbox, loading, setEntries, setActiveSandbox, refreshThread } = useThreadData(brainThreadId, runStarted, initialEntries);

  const { runtimeStatus, isRunning, handleSendMessage, handleStopStreaming } =
    useStreamHandler({
      threadId: brainThreadId,
      conversationId: conversation?.id,
      refreshThreads: tm.refreshThreads,
      onUpdate: (updater) => setEntries(updater),
      loading,
      runStarted,
    });

  const { tasks, refresh: refreshTasks } = useBackgroundTasks({ threadId: brainThreadId, loading, refreshThreads: tm.refreshThreads });

  const isStreaming = isRunning;

  const { sandboxActionError, handlePauseSandbox, handleResumeSandbox } =
    useSandboxManager({
      activeThreadId: brainThreadId,
      isStreaming,
      activeSandbox,
      setActiveSandbox,
      loadThread: refreshThread,
    });

  const ui = useAppActions({ activeThreadId: brainThreadId, setEntries });
  const {
    computerOpen, computerTab,
    setComputerOpen, setComputerTab,
    handleFocusAgent, handleSendQueueMessage,
  } = ui;

  const handleTaskNoticeClick = useCallback(
    (taskId: string) => {
      for (const entry of entries) {
        if (entry.role !== "assistant") continue;
        for (const seg of (entry as AssistantTurn).segments) {
          if (seg.type === "tool" && seg.step.name === "Agent" && seg.step.subagent_stream?.task_id === taskId) {
            handleFocusAgent(seg.step.id);
            return;
          }
        }
      }
    },
    [entries, handleFocusAgent],
  );

  const handleCancelTask = useCallback(
    async (taskId: string) => {
      try {
        const response = await fetch(`/api/threads/${brainThreadId}/tasks/${taskId}/cancel`, {
          method: "POST",
        });
        if (!response.ok) {
          console.error("[ChatPage] Failed to cancel task:", response.statusText);
        } else {
          await refreshTasks();
        }
      } catch (err) {
        console.error("[ChatPage] Error cancelling task:", err);
      }
    },
    [brainThreadId, refreshTasks],
  );

  const computerResize = useResizableX(600, 360, 1200, true);

  return (
    <>
      <Header
        activeThreadId={brainThreadId}
        threadPreview={conversation?.title ?? tm.threads.find((t) => t.thread_id === threadId)?.preview ?? null}
        sandboxInfo={activeSandbox}
        currentModel={currentModel}
        onToggleSidebar={() => setSidebarCollapsed(v => !v)}
        onPauseSandbox={() => void handlePauseSandbox()}
        onResumeSandbox={() => void handleResumeSandbox()}
        onModelChange={setCurrentModel}
      />

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 flex flex-col min-w-[320px]">
          {sandboxActionError && (
            <div className="px-3 py-2 text-xs bg-red-50 text-red-600 border-b border-red-200">
              {sandboxActionError}
            </div>
          )}
          <div className="relative flex-1 flex flex-col min-h-0">
            <BackgroundSessionsIndicator tasks={tasks} onCancelTask={handleCancelTask} />
            {/* @@@view-mode-toggle - only owner of the agent can toggle full view */}
            {conversation && isOwnAgent && (
              <div className="flex items-center justify-end px-4 py-1 border-b border-border/50 bg-muted/20">
                <button
                  onClick={() => setViewMode(v => v === "owner" ? "contact" : "owner")}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  title={viewMode === "owner" ? "切换到联系人视图" : "切换到完整视图"}
                >
                  {viewMode === "owner" ? <Eye className="w-3.5 h-3.5" /> : <MessageSquareText className="w-3.5 h-3.5" />}
                  {viewMode === "owner" ? "完整视图" : "消息视图"}
                </button>
              </div>
            )}
            {/* @@@two-views - owner reads brain thread, contact reads conversation_messages */}
            {viewMode === "contact" && conversation ? (
              <ConversationView conversationId={conversation.id} isStreaming={isStreaming} />
            ) : (
              <ChatArea
                entries={entries}
                isStreaming={isStreaming}
                runtimeStatus={runtimeStatus}
                loading={loading}
                onFocusAgent={handleFocusAgent}
                onTaskNoticeClick={handleTaskNoticeClick}
              />
            )}
          </div>
          <TaskProgress
            isStreaming={isStreaming}
            runtimeStatus={runtimeStatus}
            sandboxType={activeSandbox?.type ?? "local"}
            sandboxStatus={activeSandbox?.status ?? (activeSandbox?.type === "local" ? "running" : null)}
            computerOpen={computerOpen}
            onToggleComputer={() => setComputerOpen((v) => !v)}
          />
          <InputBox
            disabled={isStreaming}
            isStreaming={isStreaming}
            placeholder="告诉 Leon 你需要什么帮助..."
            onSendMessage={(msg) => void handleSendMessage(msg)}
            onSendQueueMessage={handleSendQueueMessage}
            onStop={handleStopStreaming}
          />
          <TokenStats runtimeStatus={runtimeStatus} />
        </div>

        {computerOpen && (
          <>
            <DragHandle onMouseDown={computerResize.onMouseDown} />
            <ComputerPanel
              isOpen={computerOpen}
              onClose={() => setComputerOpen(false)}
              threadId={brainThreadId}
              sandboxType={activeSandbox?.type ?? null}
              chatEntries={entries}
              width={computerResize.width}
              activeTab={computerTab}
              onTabChange={setComputerTab}
              isStreaming={isStreaming}
            />
          </>
        )}
      </div>
    </>
  );
}
