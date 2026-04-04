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
  threadTitle: string | null;
  sandboxInfo: SandboxInfo | null;
  currentModel?: string;
  onToggleSidebar: () => void;
  onPauseSandbox: () => void;
  onResumeSandbox: () => void;
  onModelChange?: (model: string) => void;
}

export default function Header({
  activeThreadId,
  threadTitle,
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
    ? "hsl(var(--success))"
    : sandboxInfo?.status === "paused"
      ? "hsl(var(--warning))"
      : "hsl(var(--muted-foreground))";

  return (
    <header className="h-12 flex items-center justify-between px-4 flex-shrink-0 bg-card border-b border-border">
      <div className="flex items-center gap-3 min-w-0">
        {isMobile ? (
          <button
            onClick={() => navigate("/threads")}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
        ) : (
          <button
            onClick={onToggleSidebar}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
        )}

        {/* Thread title + optional sandbox badge */}
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-foreground truncate max-w-[200px]">
            {threadTitle || (activeThreadId ? "对话" : "无对话")}
          </span>
          {/* Show sandbox as a small badge only for remote sandboxes */}
          {hasRemote && sandboxInfo?.status && (
            <span
              className="hidden sm:inline-flex items-center gap-1 text-2xs px-1.5 py-0.5 rounded-md font-medium border border-border text-muted-foreground bg-muted flex-shrink-0"
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
            className="px-3 py-1.5 rounded-lg text-xs flex items-center gap-2 border border-border text-foreground-secondary hover:bg-muted hover:text-foreground"
            onClick={onPauseSandbox}
          >
            <Pause className="w-3.5 h-3.5" />
            暂停
          </button>
        )}
        {hasRemote && sandboxInfo?.status === "paused" && (
          <button
            className="px-3 py-1.5 rounded-lg text-xs flex items-center gap-2 border border-border text-foreground-secondary hover:bg-muted hover:text-foreground"
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
