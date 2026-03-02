import { ChevronLeft, PanelLeft, Pause, Play } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { SandboxInfo } from "../api";
import { useIsMobile } from "../hooks/use-mobile";
import ModelSelector from "./ModelSelector";

const KNOWN_LABELS: Record<string, string> = {
  local: "本地", agentbay: "AgentBay", daytona: "Daytona", docker: "Docker", e2b: "E2B",
};
function sandboxLabel(name: string): string {
  return KNOWN_LABELS[name]
    ?? name
      .split(/[_-]+/)
      .filter(Boolean)
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
}

interface HeaderProps {
  activeThreadId: string | null;
  threadPreview: string | null;
  sandboxInfo: SandboxInfo | null;
  currentModel?: string;
  onToggleSidebar: () => void;
  onPauseSandbox: () => void;
  onResumeSandbox: () => void;
  onModelChange?: (model: string) => void;
}

export default function Header({
  activeThreadId,
  threadPreview,
  sandboxInfo,
  currentModel = "leon:medium",
  onToggleSidebar,
  onPauseSandbox,
  onResumeSandbox,
  onModelChange,
}: HeaderProps) {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const hasRemote = sandboxInfo && sandboxInfo.type !== "local";
  const sandboxLabelText = sandboxLabel(sandboxInfo?.type ?? "local");
  const statusDotColor = sandboxInfo?.status === "running"
    ? "#22c55e"
    : sandboxInfo?.status === "paused"
      ? "#eab308"
      : "#a3a3a3";

  return (
    <header className="h-12 flex items-center justify-between px-4 flex-shrink-0 bg-white border-b border-[#e5e5e5]">
      <div className="flex items-center gap-3 min-w-0">
        {isMobile ? (
          <button
            onClick={() => navigate("/chat")}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[#737373] hover:bg-[#f5f5f5] hover:text-[#171717]"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
        ) : (
          <button
            onClick={onToggleSidebar}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[#737373] hover:bg-[#f5f5f5] hover:text-[#171717]"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
        )}

        {/* Thread title + optional sandbox badge */}
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-[#171717] truncate max-w-[200px]">
            {threadPreview || (activeThreadId ? "新对话" : "无对话")}
          </span>
          {/* Show sandbox as a small badge only for remote sandboxes */}
          {hasRemote && sandboxInfo?.status && (
            <span
              className="hidden sm:inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md font-medium border border-[#e5e5e5] text-[#737373] bg-[#fafafa] flex-shrink-0"
              title={`沙箱: ${sandboxLabelText}`}
            >
              <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: statusDotColor }} />
              {sandboxLabelText}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <ModelSelector
          currentModel={currentModel}
          threadId={activeThreadId}
          onModelChange={onModelChange}
        />

        {hasRemote && sandboxInfo?.status === "running" && (
          <button
            className="px-3 py-1.5 rounded-lg text-xs flex items-center gap-2 border border-[#e5e5e5] text-[#525252] hover:bg-[#f5f5f5] hover:text-[#171717]"
            onClick={onPauseSandbox}
          >
            <Pause className="w-3.5 h-3.5" />
            暂停
          </button>
        )}
        {hasRemote && sandboxInfo?.status === "paused" && (
          <button
            className="px-3 py-1.5 rounded-lg text-xs flex items-center gap-2 border border-[#e5e5e5] text-[#525252] hover:bg-[#f5f5f5] hover:text-[#171717]"
            onClick={onResumeSandbox}
          >
            <Play className="w-3.5 h-3.5" />
            恢复
          </button>
        )}
      </div>
    </header>
  );
}
