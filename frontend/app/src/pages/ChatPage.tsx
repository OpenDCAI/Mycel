import { useCallback, useEffect, useState } from "react";
import { useParams, useOutletContext, useLocation } from "react-router-dom";
import { toast } from "sonner";
import ChatArea from "../components/ChatArea";
import type { AssistantTurn } from "../api";
import { uploadWorkspaceFile } from "../api";
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

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
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
  const { tm, setSidebarCollapsed } = useOutletContext<OutletContext>();
  const userName = useAuthStore(s => s.user?.name);
  const userId = useAuthStore(s => s.user?.id);
  const userHasAvatar = useAuthStore(s => !!s.user?.avatar);

  // Derive avatar URLs from thread data
  const currentThread = tm.threads.find(t => t.thread_id === threadId);
  const agentName = currentThread?.entity_name ?? currentThread?.member_name;
  const agentAvatarUrl = currentThread?.avatar_url;
  const userAvatarUrl = userHasAvatar && userId ? `/api/members/${userId}/avatar` : undefined;
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

  const state = location.state as { selectedModel?: string; runStarted?: boolean; message?: string } | null;
  const [currentModel, setCurrentModel] = useState<string>(state?.selectedModel ?? "");

  // location.state.runStarted is set by NewChatPage on SPA navigation only.
  // On page refresh the browser preserves state but React Router resets it to null,
  // so state?.runStarted will already be falsy after a real reload — no navEntry check needed.
  const runStarted = !!state?.runStarted;

  // Pre-populate user + empty assistant turn so ThinkingIndicator shows immediately (no skeleton).
  // The empty assistant turn (streaming=true, segments=[]) renders the three-dot indicator
  // until stream events arrive and populate it.
  const [initialEntries] = useState(() => {
    if (!runStarted || !state?.message) return undefined;
    const now = Date.now();
    return [
      { id: `user-${now}`, role: "user" as const, content: state.message, timestamp: now },
      { id: `assistant-${now + 1}`, role: "assistant" as const, segments: [], streaming: true, timestamp: now + 1 } as AssistantTurn,
    ];
  });

  useEffect(() => {
    if (state?.selectedModel) return;
    authFetch(`/api/threads/${threadId}/runtime`)
      .then((r) => r.json())
      .then((d) => {
        if (d.model) {
          setCurrentModel(d.model);
          return;
        }
        return fetch("/api/settings")
          .then((r) => r.json())
          .then((settings) => setCurrentModel(settings.default_model || "leon:large"));
      })
      .catch(() => setCurrentModel("leon:large"));
  }, [state?.selectedModel, threadId]);

  const { entries, activeSandbox, loading, setEntries, setActiveSandbox, refreshThread } = useThreadData(threadId, runStarted, initialEntries);

  const { runtimeStatus, isRunning, handleSendMessage, handleStopStreaming } =
    useStreamHandler({
      threadId,
      // Use tm.refreshThreads (sidebar list only) — NOT refreshThread (which calls
      // setEntries(history) and would wipe any in-flight streaming entries for the next run).
      refreshThreads: tm.refreshThreads,
      onUpdate: (updater) => setEntries(updater),
      loading,
      runStarted,
    });

  // @@@debug-entries — expose current entries for backend comparison
  useEffect(() => {
    (window as Window & { __debugEntries?: () => unknown[] }).__debugEntries =
      () => JSON.parse(JSON.stringify(entries)) as unknown[];
  }, [entries]);

  const { tasks, refresh: refreshTasks } = useBackgroundTasks({ threadId, loading, refreshThreads: tm.refreshThreads });

  const isStreaming = isRunning;

  const { sandboxActionError, handlePauseSandbox, handleResumeSandbox } =
    useSandboxManager({
      activeThreadId: threadId,
      isStreaming,
      activeSandbox,
      setActiveSandbox,
      loadThread: refreshThread,
    });

  const ui = useAppActions({ activeThreadId: threadId });
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
          if (seg.type === "tool" && seg.step.name === "Task" && seg.step.subagent_stream?.task_id === taskId) {
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
        const response = await fetch(`/api/threads/${threadId}/tasks/${taskId}/cancel`, {
          method: "POST",
        });
        if (!response.ok) {
          console.error("[ChatPage] Failed to cancel task:", response.statusText);
        } else {
          // 取消成功后刷新任务列表
          await refreshTasks();
        }
      } catch (err) {
        console.error("[ChatPage] Error cancelling task:", err);
      }
    },
    [threadId, refreshTasks],
  );

  const computerResize = useResizableX(600, 360, 1200, true);

  async function handleUploadFiles(files: File[]): Promise<void> {
    const toastId = toast.loading(`Uploading ${files.length} file(s)...`);
    try {
      for (const file of files) {
        await uploadWorkspaceFile(threadId, {
          file,
          path: file.name,
        });
      }
      toast.success(`Uploaded ${files.length} file(s)`, { id: toastId });
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      toast.error(`Upload failed: ${msg}`, { id: toastId });
      throw error;
    }
  }

  async function handleSendWithAttachments(message: string): Promise<void> {
    const filenames = attachedFiles.map((f) => f.name);
    if (attachedFiles.length > 0) {
      await handleUploadFiles(attachedFiles);
      setAttachedFiles([]);
    }
    await handleSendMessage(message, filenames.length > 0 ? filenames : undefined);
  }

  return (
    <>
      <Header
        activeThreadId={threadId}
        threadTitle={currentThread?.entity_name ?? null}
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
            <ChatArea
              entries={entries}
              isStreaming={isStreaming}
              runtimeStatus={runtimeStatus}
              loading={loading}
              onFocusAgent={handleFocusAgent}
              onTaskNoticeClick={handleTaskNoticeClick}
            />
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
            onSendMessage={(msg) => void handleSendWithAttachments(msg)}
            onSendQueueMessage={handleSendQueueMessage}
            onStop={handleStopStreaming}
            attachedFiles={attachedFiles}
            onAttachFiles={(files) => setAttachedFiles((prev) => [...prev, ...files])}
            onRemoveFile={(index) => setAttachedFiles((prev) => prev.filter((_, i) => i !== index))}
          />
          <TokenStats runtimeStatus={runtimeStatus} />
        </div>

        {computerOpen && (
          <>
            <DragHandle onMouseDown={computerResize.onMouseDown} />
            <ComputerPanel
              isOpen={computerOpen}
              onClose={() => setComputerOpen(false)}
              threadId={threadId}
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
