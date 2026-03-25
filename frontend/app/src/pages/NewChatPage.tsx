import { useState } from "react";
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

export default function NewChatPage() {
  const navigate = useNavigate();
  const { memberId: memberUrlId } = useParams<{ memberId: string }>();
  const { tm } = useOutletContext<OutletContext>();
  const { sandboxTypes, selectedSandbox, handleCreateThread } = tm;
  const { settings, loading, hasWorkspace, refreshSettings } = useWorkspaceSettings();
  const [showWorkspaceSetup, setShowWorkspaceSetup] = useState(false);

  const authAgent = useAuthStore(s => s.agent);
  const memberList = useAppStore(s => s.memberList);

  // Resolve URL member name → member ID
  const decodedName = memberUrlId ? decodeURIComponent(memberUrlId) : undefined;
  const isOwnedAgent = !decodedName || decodedName === authAgent?.name;
  const memberName = isOwnedAgent ? (authAgent?.name || "Agent") : decodedName;

  // Get the actual member ID for thread creation
  const resolvedMember = isOwnedAgent
    ? memberList.find(m => m.id === authAgent?.id)
    : memberList.find(m => m.name === decodedName);
  const resolvedMemberId = isOwnedAgent ? authAgent?.id : resolvedMember?.id;
  const memberAvatarUrl = resolvedMember?.avatar_url;

  async function handleSend(message: string, sandbox: string, model: string, workspace?: string) {
    if (sandbox === "local" && !workspace && !hasWorkspace) {
      setShowWorkspaceSetup(true);
      return;
    }
    if (!resolvedMemberId) {
      console.error("[NewChatPage] Cannot create thread: no member ID resolved");
      return;
    }

    const cwd = workspace || settings?.default_workspace || undefined;
    const threadId = await handleCreateThread(sandbox, cwd, resolvedMemberId);
    postRun(threadId, message, undefined, model ? { model } : undefined).catch(err => {
      console.error('[NewChatPage] postRun failed:', err);
    });
    navigate(`/threads/${memberUrlId}/${threadId}`, {
      state: { selectedModel: model, runStarted: true, message },
    });
  }

  async function handleWorkspaceSet(_workspace: string) {
    await refreshSettings();
    setShowWorkspaceSetup(false);
  }

  if (loading) {
    return null;
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
            {isOwnedAgent ? "你的通用数字成员，随时准备为你工作" : `${memberName} 准备为你工作`}
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
