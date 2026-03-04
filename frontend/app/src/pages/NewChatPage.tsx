import { useState } from "react";
import { useNavigate, useOutletContext, useLocation } from "react-router-dom";
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
  const location = useLocation();
  const { tm } = useOutletContext<OutletContext>();
  const { sandboxTypes, selectedSandbox, handleCreateThread } = tm;
  const { settings, loading, hasWorkspace } = useWorkspaceSettings();
  const [showWorkspaceSetup, setShowWorkspaceSetup] = useState(false);

  const startWith = (location.state as any)?.startWith as string | undefined;
  const memberName = (location.state as any)?.memberName as string | undefined;
  const agentForThread = startWith && startWith !== "__leon__" ? startWith : undefined;

  async function handleSend(message: string, sandbox: string, model: string, workspace?: string) {
    // For local sandbox, check if workspace is set
    if (sandbox === "local" && !workspace && !hasWorkspace) {
      setShowWorkspaceSetup(true);
      return;
    }

    const cwd = workspace || settings?.default_workspace || undefined;
    const threadId = await handleCreateThread(sandbox, cwd, agentForThread);
    console.log('[NewChatPage] Created thread:', threadId, 'agent:', agentForThread, 'posting run:', message);
    try {
      await postRun(threadId, message, undefined, model ? { model } : undefined);
    } catch (err) {
      console.error('[NewChatPage] postRun failed:', err);
    }
    navigate(`/chat/${threadId}`, {
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
