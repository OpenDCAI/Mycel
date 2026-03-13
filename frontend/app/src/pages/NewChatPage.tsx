import { useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import CenteredInputBox from "../components/CenteredInputBox";
import WorkspaceSetupModal from "../components/WorkspaceSetupModal";
import type { ThreadManagerState, ThreadManagerActions } from "../hooks/use-thread-manager";
import { useWorkspaceSettings } from "../hooks/use-workspace-settings";
import { useAuthStore } from "../store/auth-store";
import { createConversation, sendConversationMessage } from "../api/conversations";
import type { ConversationSummary } from "../api/conversations";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
  conversations: ConversationSummary[];
  refreshConversations: () => Promise<void>;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
  setSessionsOpen: (value: boolean) => void;
}

export default function NewChatPage() {
  const navigate = useNavigate();
  const { memberId } = useParams<{ memberId: string }>();
  const { tm, conversations, refreshConversations } = useOutletContext<OutletContext>();
  const { sandboxTypes, selectedSandbox } = tm;
  const { settings, loading, hasWorkspace } = useWorkspaceSettings();
  const [showWorkspaceSetup, setShowWorkspaceSetup] = useState(false);
  const agent = useAuthStore(s => s.agent);

  const memberName = memberId === "leon" ? undefined : memberId;

  async function handleSend(message: string, sandbox: string, model: string, workspace?: string) {
    if (sandbox === "local" && !workspace && !hasWorkspace) {
      setShowWorkspaceSetup(true);
      return;
    }

    // @@@conversation-flow - resolve target agent from URL memberId, fall back to own agent.
    // Clicking "alice's Leon" group header → memberId="alice's Leon" → create conv with alice's Leon.
    // Clicking "leon" (default) → create conv with own agent.
    let targetAgentId = agent?.id;
    if (memberId && memberId !== "leon" && conversations) {
      const match = conversations.find(c => c.agent_name === memberId);
      if (match) targetAgentId = match.agent_member_id;
    }
    if (!targetAgentId) {
      console.error("[NewChatPage] No agent to create conversation with");
      return;
    }

    const conv = await createConversation(targetAgentId);
    sendConversationMessage(conv.id, message).catch(err => {
      console.error("[NewChatPage] sendConversationMessage failed:", err);
    });
    void refreshConversations();
    navigate(`/chat/${memberId}/${conv.id}`, {
      state: { selectedModel: model, runStarted: true, message },
    });
  }

  function handleWorkspaceSet(_workspace: string) {
    setShowWorkspaceSetup(false);
  }

  if (loading) {
    return null;
  }

  return (
    <div className="flex-1 flex items-center justify-center relative">
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[600px] px-4">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-medium text-foreground mb-2">
            你好，我是 {memberName || "Leon"}
          </h1>
          <p className="text-sm text-muted-foreground mb-6">
            {memberName && memberName !== "Leon" ? `${memberName} 准备为你工作` : "你的通用数字成员，随时准备为你工作"}
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
