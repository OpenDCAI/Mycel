import { useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { postRun } from "../api";
import CenteredInputBox from "../components/CenteredInputBox";
import WorkspaceSetupModal from "../components/WorkspaceSetupModal";
import type { ThreadManagerState, ThreadManagerActions } from "../hooks/use-thread-manager";
import { useWorkspaceSettings } from "../hooks/use-workspace-settings";
import { useAuthStore } from "../store/auth-store";
import { useAppStore } from "../store/app-store";
import MemberAvatar from "../components/MemberAvatar";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
  setSessionsOpen: (value: boolean) => void;
}

export default function NewChatPage({ mode = "member" }: { mode?: "member" | "new" }) {
  const navigate = useNavigate();
  const { memberId } = useParams<{ memberId: string }>();
  const { tm } = useOutletContext<OutletContext>();
  const { sandboxTypes, selectedSandbox, handleCreateThread, handleGetMainThread } = tm;
  const { settings, loading, hasWorkspace, refreshSettings } = useWorkspaceSettings();
  const shouldResolveMain = mode === "member";
  const [error, setError] = useState<string | null>(null);
  const [resolveState, setResolveState] = useState<"resolving" | "ready" | "error">(
    shouldResolveMain ? "resolving" : "ready",
  );
  const [showWorkspaceSetup, setShowWorkspaceSetup] = useState(false);

  const authAgent = useAuthStore(s => s.agent);
  const memberList = useAppStore(s => s.memberList);
  const decodedMemberId = memberId ? decodeURIComponent(memberId) : null;
  const resolvedMember = decodedMemberId ? memberList.find(m => m.id === decodedMemberId) : undefined;
  const isOwnedAgent = decodedMemberId === authAgent?.id;
  const memberName = resolvedMember?.name ?? (isOwnedAgent ? (authAgent?.name || "Agent") : "Agent");
  const memberAvatarUrl = resolvedMember?.avatar_url;

  useEffect(() => {
    if (!shouldResolveMain) return;

    let cancelled = false;

    async function resolveMainThread() {
      if (!decodedMemberId) {
        setError("Missing member ID");
        setResolveState("error");
        return;
      }

      try {
        const thread = await handleGetMainThread(decodedMemberId);
        if (cancelled) return;
        if (thread) {
          navigate(`/threads/${encodeURIComponent(decodedMemberId)}/${thread.thread_id}`, { replace: true });
          return;
        }
        setResolveState("ready");
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Failed to resolve main thread";
        console.error("[NewChatPage] resolve main thread failed:", err);
        setError(message);
        setResolveState("error");
      }
    }

    void resolveMainThread();
    return () => {
      cancelled = true;
    };
  }, [decodedMemberId, handleGetMainThread, navigate, shouldResolveMain]);

  async function handleSend(message: string, sandbox: string, model: string, workspace?: string) {
    if (sandbox === "local" && !workspace && !hasWorkspace) {
      setShowWorkspaceSetup(true);
      return;
    }
    if (!decodedMemberId) {
      throw new Error("Cannot create thread without member ID");
    }

    const cwd = workspace || settings?.default_workspace || undefined;
    const threadId = await handleCreateThread(sandbox, cwd, decodedMemberId, model);
    postRun(threadId, message, undefined, model ? { model } : undefined).catch(err => {
      console.error("[NewChatPage] postRun failed:", err);
    });
    navigate(`/threads/${encodeURIComponent(decodedMemberId)}/${threadId}`, {
      state: { selectedModel: model, runStarted: true, message },
    });
  }

  async function handleWorkspaceSet(_workspace: string) {
    await refreshSettings();
    setShowWorkspaceSetup(false);
  }

  if (loading || resolveState === "resolving") {
    return (
      <div className="flex-1 flex items-center justify-center relative">
        <div className="w-full max-w-[420px] px-6 text-center">
          <div className="flex justify-center mb-4">
            <MemberAvatar name={memberName} avatarUrl={memberAvatarUrl} type="mycel_agent" size="lg" />
          </div>
          <h1 className="text-xl font-medium text-foreground mb-2">
            正在检查 {memberName} 的主对话
          </h1>
          <p className="text-sm text-muted-foreground">
            如果没有主对话，这里会进入创建界面。
          </p>
        </div>
      </div>
    );
  }

  if (resolveState === "error") {
    return (
      <div className="flex-1 flex items-center justify-center relative">
        <div className="w-full max-w-[420px] px-6 text-center">
          <div className="flex justify-center mb-4">
            <MemberAvatar name={memberName} avatarUrl={memberAvatarUrl} type="mycel_agent" size="lg" />
          </div>
          <h1 className="text-xl font-medium text-foreground mb-2">
            无法检查 {memberName} 的主对话
          </h1>
          <p className="text-sm text-destructive">
            {error ?? "Unknown error"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex items-center justify-center relative">
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[600px] px-4">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <MemberAvatar name={memberName} avatarUrl={memberAvatarUrl} type="mycel_agent" size="lg" />
          </div>
          <h1 className="text-2xl font-medium text-foreground mb-2">
            你好，我是 {memberName}
          </h1>
          <p className="text-sm text-muted-foreground mb-6">
            {mode === "new"
              ? `为 ${memberName} 创建一个新对话`
              : isOwnedAgent
                ? "你的通用数字成员，随时准备为你工作"
                : `${memberName} 准备为你工作`}
          </p>

          <div className="flex flex-wrap justify-center gap-2">
            <div className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs text-muted-foreground">
              文件操作
            </div>
            <div className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs text-muted-foreground">
              代码探索
            </div>
            <div className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs text-muted-foreground">
              命令执行
            </div>
            <div className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs text-muted-foreground">
              信息检索
            </div>
          </div>
        </div>

        <CenteredInputBox
          sandboxTypes={sandboxTypes}
          defaultSandbox={selectedSandbox}
          defaultWorkspace={settings?.default_workspace || undefined}
          defaultModel={settings?.default_model || "leon:large"}
          recentWorkspaces={settings?.recent_workspaces || []}
          enabledModels={settings?.enabled_models || []}
          onSend={handleSend}
        />
      </div>

      <WorkspaceSetupModal
        open={showWorkspaceSetup}
        onClose={() => setShowWorkspaceSetup(false)}
        onWorkspaceSet={handleWorkspaceSet}
      />
    </div>
  );
}
