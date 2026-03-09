import { useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { postRun } from "../api";
import CenteredInputBox from "../components/CenteredInputBox";
import WorkspaceSetupModal from "../components/WorkspaceSetupModal";
import type { ThreadManagerState, ThreadManagerActions } from "../hooks/use-thread-manager";
import { useWorkspaceSettings } from "../hooks/use-workspace-settings";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
  setSessionsOpen: (value: boolean) => void;
}

export default function NewChatPage() {
  const navigate = useNavigate();
  const { memberId } = useParams<{ memberId: string }>();
  const { tm } = useOutletContext<OutletContext>();
  const { sandboxTypes, selectedSandbox, handleCreateThread } = tm;
  const { settings, loading, hasWorkspace } = useWorkspaceSettings();
  const [showWorkspaceSetup, setShowWorkspaceSetup] = useState(false);

  // memberId in URL is the member name (e.g. "Test Researcher") or "leon" for the default agent
  const memberName = memberId === "leon" ? undefined : memberId;
  const agentForThread = memberName;

  async function handleSend(message: string, sandbox: string, model: string, workspace?: string) {
    // For local sandbox, check if workspace is set
    if (sandbox === "local" && !workspace && !hasWorkspace) {
      setShowWorkspaceSetup(true);
      return;
    }

    const cwd = workspace || settings?.default_workspace || undefined;
    const threadId = await handleCreateThread(sandbox, cwd, agentForThread);
    // Fire-and-forget: don't await postRun — agent creation can take 3-5s on first call.
    // ChatPage mounts immediately with optimistic spinner; SSE (seq=0) picks up run_start
    // when the agent is ready.
    postRun(threadId, message, undefined, model ? { model } : undefined).catch(err => {
      console.error('[NewChatPage] postRun failed:', err);
    });
    navigate(`/chat/${memberId}/${threadId}`, {
      state: { selectedModel: model, runStarted: true, message },
    });
  }

  function handleWorkspaceSet(_workspace: string) {
    setShowWorkspaceSetup(false);
    // Workspace is now set, user can try sending again
  }

  if (loading) {
    return null;
  }

  return (
    <div className="flex-1 flex items-center justify-center relative">
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[600px] px-4">
        {/* Welcome Section */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-medium text-foreground mb-2">
            你好，我是 {memberName || "Leon"}
          </h1>
          <p className="text-sm text-muted-foreground mb-6">
            {memberName && memberName !== "Leon" ? `${memberName} 准备为你工作` : "你的通用数字成员，随时准备为你工作"}
          </p>

          {/* Capability Tags */}
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

        {/* Input Box */}
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
