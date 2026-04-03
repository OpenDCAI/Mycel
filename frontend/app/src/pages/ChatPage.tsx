import { useCallback, useEffect, useState } from "react";
import { useParams, useOutletContext, useLocation } from "react-router-dom";
import { Check, ShieldAlert, X } from "lucide-react";
import { toast } from "sonner";
import ChatArea from "../components/ChatArea";
import type { AssistantTurn } from "../api";
import { uploadSandboxFile } from "../api";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import ComputerPanel from "../components/ComputerPanel";
import { DragHandle } from "../components/DragHandle";
import Header from "../components/Header";
import InputBox from "../components/InputBox";
import TaskProgress from "../components/TaskProgress";
import TokenStats from "../components/TokenStats";
import { authFetch, useAuthStore } from "../store/auth-store";
import { useAppActions } from "../hooks/use-app-actions";
import { useBackgroundTasks } from "../hooks/use-background-tasks";
import { BackgroundSessionsIndicator } from "../components/chat-area/BackgroundSessionsIndicator";
import { useResizableX } from "../hooks/use-resizable-x";
import { useSandboxManager } from "../hooks/use-sandbox-manager";
import { useDisplayDeltas } from "../hooks/use-display-deltas";
import { useThreadData } from "../hooks/use-thread-data";
import { useThreadPermissions } from "../hooks/use-thread-permissions";
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

  // @@@display-builder — no optimistic initialEntries.
  // Backend sends user_message + run_start via display_delta.
  const initialEntries = undefined;

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

  const { entries, activeSandbox, loading, displaySeq, setEntries, setActiveSandbox, refreshThread } = useThreadData(threadId, runStarted, initialEntries);
  const {
    requests: pendingPermissionRequests,
    resolvingId,
    resolvePermission,
  } = useThreadPermissions(threadId);

  const { runtimeStatus, isRunning, handleSendMessage, handleStopStreaming } =
    useDisplayDeltas({
      threadId,
      refreshThreads: tm.refreshThreads,
      onUpdate: (updater) => setEntries(updater),
      loading,
      runStarted,
      displaySeq,
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
        const response = await authFetch(`/api/threads/${threadId}/tasks/${taskId}/cancel`, {
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
    [threadId, refreshTasks],
  );

  const computerResize = useResizableX(600, 360, 1200, true);
  const currentPermissionRequest = pendingPermissionRequests[0] ?? null;

  const handleResolvePermission = useCallback(
    async (decision: "allow" | "deny") => {
      if (!currentPermissionRequest) return;
      try {
        await resolvePermission(currentPermissionRequest.request_id, decision);
        await refreshThread();
        toast.success(decision === "allow" ? "已批准该权限请求" : "已拒绝该权限请求");
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        toast.error(`权限处理失败: ${message}`);
      }
    },
    [currentPermissionRequest, refreshThread, resolvePermission],
  );

  // @@@workspace-upload — upload attached files then send message with attachment filenames
  async function handleSendWithAttachments(message: string): Promise<void> {
    const filenames = attachedFiles.map((f) => f.name);
    if (attachedFiles.length > 0) {
      const toastId = toast.loading(`Uploading ${attachedFiles.length} file(s)...`);
      try {
        await Promise.all(attachedFiles.map((file) =>
          uploadSandboxFile(threadId, { file, path: file.name }),
        ));
        toast.success(`Uploaded ${attachedFiles.length} file(s)`, { id: toastId });
        setAttachedFiles([]);
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        toast.error(`Upload failed: ${msg}`, { id: toastId });
        return;
      }
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
            <div className="px-3 py-2 text-xs bg-destructive/10 text-destructive border-b border-destructive/20">
              {sandboxActionError}
            </div>
          )}
          {currentPermissionRequest && (
            <div className="px-3 py-2 border-b border-warning/20 bg-warning/5">
              <div className="max-w-3xl mx-auto">
                <Alert className="border-warning/20 bg-transparent px-0 py-0">
                  <ShieldAlert className="text-warning" />
                  <AlertTitle>权限确认：{currentPermissionRequest.tool_name}</AlertTitle>
                  <AlertDescription>
                    <p>{currentPermissionRequest.message || "该工具需要你明确批准后才能继续。"}</p>
                    <p className="text-xs text-muted-foreground">
                      处理后不会自动重跑；Leon 需要在下一次相同操作时继续执行。
                    </p>
                    <code className="block w-full overflow-x-auto rounded-md bg-background/80 px-2 py-1 text-xs text-foreground border border-border/60">
                      {JSON.stringify(currentPermissionRequest.args)}
                    </code>
                    {pendingPermissionRequests.length > 1 && (
                      <p className="text-xs text-muted-foreground">
                        还有 {pendingPermissionRequests.length - 1} 条待处理请求。
                      </p>
                    )}
                    <div className="flex items-center gap-2 pt-1">
                      <Button
                        size="sm"
                        onClick={() => void handleResolvePermission("allow")}
                        disabled={resolvingId === currentPermissionRequest.request_id}
                      >
                        <Check className="w-4 h-4" />
                        批准
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void handleResolvePermission("deny")}
                        disabled={resolvingId === currentPermissionRequest.request_id}
                      >
                        <X className="w-4 h-4" />
                        拒绝
                      </Button>
                    </div>
                  </AlertDescription>
                </Alert>
              </div>
            </div>
          )}
          <div className="relative flex-1 flex flex-col min-h-0">
            <BackgroundSessionsIndicator tasks={tasks} onCancelTask={handleCancelTask} />
            <ChatArea
              entries={entries}
              runtimeStatus={runtimeStatus}
              loading={loading}
              onFocusAgent={handleFocusAgent}
              onTaskNoticeClick={handleTaskNoticeClick}
              agentName={agentName}
              agentAvatarUrl={agentAvatarUrl}
              userName={userName}
              userAvatarUrl={userAvatarUrl}
            />
          </div>
          <TaskProgress
            isStreaming={isStreaming}
            runtimeStatus={runtimeStatus}
            sandboxType={activeSandbox?.type ?? "local"}
            sandboxStatus={activeSandbox?.status ?? null}
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
