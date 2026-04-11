import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useOutletContext, useLocation } from "react-router-dom";
import { Check, ShieldAlert, X } from "lucide-react";
import { toast } from "sonner";
import ChatArea from "../components/ChatArea";
import type { AskUserAnswer, AskUserQuestionPrompt, PermissionRequest } from "../api";
import { isAssistantTurn, uploadSandboxFile } from "../api";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import ComputerPanel from "../components/computer-panel";
import { DragHandle } from "../components/DragHandle";
import Header from "../components/Header";
import InputBox from "../components/InputBox";
import TaskProgress from "../components/TaskProgress";
import TokenStats from "../components/TokenStats";
import { askUserQuestionSelectionKey, buildAskUserAnswers } from "./ask-user-question";
import { authFetch, useAuthStore } from "../store/auth-store";
import { useAppActions } from "../hooks/use-app-actions";
import { useBackgroundTasks } from "../hooks/use-background-tasks";
import { BackgroundSessionsIndicator } from "../components/chat-area/BackgroundSessionsIndicator";
import { useResizableX } from "../hooks/use-resizable-x";
import { useSandboxManager } from "../hooks/use-sandbox-manager";
import { useDisplayDeltas } from "../hooks/use-display-deltas";
import { useThreadData } from "../hooks/use-thread-data";
import { useThreadPermissions } from "../hooks/use-thread-permissions";
import { useThreadStream } from "../hooks/use-thread-stream";
import type { PermissionRuleBehavior } from "../api";
import type { ThreadManagerState, ThreadManagerActions } from "../hooks/use-thread-manager";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  setSessionsOpen: (value: boolean) => void;
}

function isAskUserQuestionRequest(
  request: PermissionRequest | null,
): request is PermissionRequest & { args: PermissionRequest["args"] & { questions: AskUserQuestionPrompt[] } } {
  return !!request && request.tool_name === "AskUserQuestion" && Array.isArray(request.args?.questions);
}

/** Thin wrapper: key={threadId} forces remount → all hook state resets naturally. */
export default function ChatPage() {
  const { threadId } = useParams<{ threadId: string }>();
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
  const threadDisplayName = currentThread?.sidebar_label ?? currentThread?.agent_name ?? null;
  const agentName = threadDisplayName ?? undefined;
  const agentAvatarUrl = currentThread?.avatar_url;
  const userAvatarUrl = userHasAvatar && userId ? `/api/users/${userId}/avatar` : undefined;
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

  const state = location.state as { selectedModel?: string; runStarted?: boolean; message?: string } | null;
  const [currentModel, setCurrentModel] = useState<string>(state?.selectedModel ?? "");
  const [defaultModel, setDefaultModel] = useState<string>("");

  // location.state.runStarted is set by NewChatPage on SPA navigation only.
  // On page refresh the browser preserves state but React Router resets it to null,
  // so state?.runStarted will already be falsy after a real reload — no navEntry check needed.
  const runStarted = !!state?.runStarted;

  // @@@display-builder — no optimistic initialEntries.
  // Backend sends user_message + run_start via display_delta.
  const initialEntries = undefined;

  const { entries, activeSandbox, loading, displaySeq, setEntries, setActiveSandbox, refreshThread } = useThreadData(threadId, runStarted, initialEntries);
  const threadStream = useThreadStream(threadId, {
    loading,
    refreshThreads: tm.refreshThreads,
    runStarted,
  });
  const {
    requests: pendingPermissionRequests,
    sessionRules,
    managedOnly,
    resolvingId,
    addSessionRule,
    removeSessionRule,
    resolvePermission,
  } = useThreadPermissions(threadId);

  const { runtimeStatus, isRunning, handleSendMessage, handleStopStreaming } =
    useDisplayDeltas({
      threadId,
      onUpdate: (updater) => setEntries(updater),
      displaySeq,
      stream: threadStream,
    });

  useEffect(() => {
    if (state?.selectedModel || runtimeStatus?.model || currentModel) return;
    if (threadStream.phase === "connecting" || threadStream.phase === "idle") return;
    authFetch("/api/settings")
      .then((r) => r.json())
      .then((settings) => setDefaultModel(settings.default_model || "leon:large"))
      .catch(() => setDefaultModel("leon:large"));
  }, [currentModel, runtimeStatus?.model, state?.selectedModel, threadStream.phase]);

  const { tasks, refresh: refreshTasks } = useBackgroundTasks({ threadId, subscribe: threadStream.subscribe });

  const isStreaming = isRunning;

  useSandboxManager({
    activeThreadId: threadId,
    isStreaming,
    activeSandbox,
    setActiveSandbox,
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
        if (!isAssistantTurn(entry)) continue;
        for (const seg of entry.segments) {
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
  const [questionSelectionsByRequest, setQuestionSelectionsByRequest] = useState<Record<string, Record<string, string[]>>>({});
  const questionSelections = useMemo(
    () => (currentPermissionRequest ? (questionSelectionsByRequest[currentPermissionRequest.request_id] ?? {}) : {}),
    [currentPermissionRequest, questionSelectionsByRequest],
  );
  const effectiveModel = (state?.selectedModel ?? runtimeStatus?.model ?? currentModel) || defaultModel;

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

  const handleQuestionSelection = useCallback(
    (questionIndex: number, question: AskUserQuestionPrompt, optionLabel: string) => {
      if (!currentPermissionRequest) return;
      const key = askUserQuestionSelectionKey(questionIndex);
      setQuestionSelectionsByRequest((prev) => {
        const currentForRequest = prev[currentPermissionRequest.request_id] ?? {};
        const current = currentForRequest[key] ?? [];
        if (question.multiSelect) {
          const next = current.includes(optionLabel)
            ? current.filter((item) => item !== optionLabel)
            : [...current, optionLabel];
          return {
            ...prev,
            [currentPermissionRequest.request_id]: { ...currentForRequest, [key]: next },
          };
        }
        return {
          ...prev,
          [currentPermissionRequest.request_id]: { ...currentForRequest, [key]: [optionLabel] },
        };
      });
    },
    [currentPermissionRequest],
  );

  const handleSubmitQuestionAnswers = useCallback(async () => {
    if (!currentPermissionRequest || !isAskUserQuestionRequest(currentPermissionRequest)) return;
    const answers: AskUserAnswer[] = buildAskUserAnswers(currentPermissionRequest.args.questions, questionSelections);
    try {
      await resolvePermission(
        currentPermissionRequest.request_id,
        "allow",
        undefined,
        answers,
        typeof currentPermissionRequest.args.annotations === "object" && currentPermissionRequest.args.annotations !== null
          ? currentPermissionRequest.args.annotations as Record<string, unknown>
          : undefined,
      );
      await refreshThread();
      toast.success("已提交回答，Leon 会继续当前任务");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      toast.error(`提交回答失败: ${message}`);
    }
  }, [currentPermissionRequest, questionSelections, refreshThread, resolvePermission]);

  const questionPrompts = isAskUserQuestionRequest(currentPermissionRequest)
    ? currentPermissionRequest.args.questions
    : [];
  const canSubmitQuestionAnswers = questionPrompts.length > 0
    && questionPrompts.every((_, index) => (questionSelections[askUserQuestionSelectionKey(index)] ?? []).length > 0);

  const handlePersistedPermissionDecision = useCallback(
    async (decision: "allow" | "deny") => {
      if (!currentPermissionRequest) return;
      try {
        await addSessionRule(decision, currentPermissionRequest.tool_name);
        await resolvePermission(currentPermissionRequest.request_id, decision);
        await refreshThread();
        toast.success(decision === "allow" ? "已为当前线程保存长期批准" : "已为当前线程保存长期拒绝");
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        toast.error(`线程权限规则保存失败: ${message}`);
      }
    },
    [addSessionRule, currentPermissionRequest, refreshThread, resolvePermission],
  );

  const activeSessionRules = ([
    ["allow", sessionRules.allow],
    ["deny", sessionRules.deny],
    ["ask", sessionRules.ask],
  ] as const).flatMap(([behavior, tools]) =>
    tools.map((toolName) => ({ behavior, toolName })),
  );

  const handleRemoveSessionRule = useCallback(
    async (behavior: PermissionRuleBehavior, toolName: string) => {
      try {
        await removeSessionRule(behavior, toolName);
        toast.success("已移除当前线程权限规则");
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        toast.error(`移除线程权限规则失败: ${message}`);
      }
    },
    [removeSessionRule],
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
        threadTitle={threadDisplayName}
        sandboxInfo={activeSandbox}
        currentModel={effectiveModel}
        onToggleSidebar={() => setSidebarCollapsed(v => !v)}
        onModelChange={setCurrentModel}
      />
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 flex flex-col min-w-[320px] min-h-0">
          {currentPermissionRequest && !isAskUserQuestionRequest(currentPermissionRequest) && (
            <div className="px-3 py-2 border-b border-warning/20 bg-warning/5">
              <div className="max-w-3xl mx-auto">
                <Alert className="border-warning/20 bg-transparent px-0 py-0">
                  <ShieldAlert className="text-warning" />
                  <AlertTitle>{`权限确认：${currentPermissionRequest.tool_name}`}</AlertTitle>
                  <AlertDescription>
                    <>
                      <p>{currentPermissionRequest.message || "该工具需要你明确批准后才能继续。"}</p>
                      <p className="text-xs text-muted-foreground">
                        处理后不会自动重跑；Leon 需要在下一次相同操作时继续执行。
                      </p>
                      <code className="block w-full overflow-x-auto rounded-md bg-background/80 px-2 py-1 text-xs text-foreground border border-border/60">
                        {JSON.stringify(currentPermissionRequest.args)}
                      </code>
                    </>
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
                      {!managedOnly && (
                        <>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => void handlePersistedPermissionDecision("allow")}
                            disabled={resolvingId === currentPermissionRequest.request_id}
                          >
                            本线程始终批准
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => void handlePersistedPermissionDecision("deny")}
                            disabled={resolvingId === currentPermissionRequest.request_id}
                          >
                            本线程始终拒绝
                          </Button>
                        </>
                      )}
                    </div>
                    {managedOnly && (
                      <p className="pt-1 text-xs text-muted-foreground">
                        当前为 managed-only 模式，不能写入线程级权限覆盖规则。
                      </p>
                    )}
                  </AlertDescription>
                </Alert>
              </div>
            </div>
          )}
          {activeSessionRules.length > 0 && (
            <div className="px-3 py-2 border-b border-border/60 bg-muted/20">
              <div className="max-w-3xl mx-auto flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-muted-foreground">本线程权限规则</span>
                {activeSessionRules.map(({ behavior, toolName }) => (
                  <Button
                    key={`${behavior}:${toolName}`}
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 gap-2 text-xs"
                    onClick={() => void handleRemoveSessionRule(behavior, toolName)}
                  >
                    <span>{behavior}:{toolName}</span>
                    <X className="w-3 h-3" />
                  </Button>
                ))}
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
              askUserQuestion={
                isAskUserQuestionRequest(currentPermissionRequest)
                  ? {
                      requestId: currentPermissionRequest.request_id,
                      promptMessage: currentPermissionRequest.message || "Leon 需要你的回答后才能继续当前任务。",
                      prompts: questionPrompts,
                      selections: questionSelections,
                      resolving: resolvingId === currentPermissionRequest.request_id,
                      canSubmit: canSubmitQuestionAnswers,
                      onSelect: handleQuestionSelection,
                      onSubmit: () => void handleSubmitQuestionAnswers(),
                      selectionKeyForIndex: askUserQuestionSelectionKey,
                    }
                  : undefined
              }
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
