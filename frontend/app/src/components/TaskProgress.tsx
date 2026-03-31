import { useState } from "react";
import type { StreamStatus } from "../api";

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

interface TaskProgressProps {
  isStreaming: boolean;
  runtimeStatus: StreamStatus | null;
  sandboxType: string | null;
  sandboxStatus: string | null;
  computerOpen?: boolean;
  onToggleComputer?: () => void;
}

function statusColor(status: string | null): string {
  if (status === "running") return "#22c55e";
  if (status === "paused") return "#eab308";
  if (status === "detached") return "#a3a3a3";
  return "#ef4444";
}

/** Retro computer icon — CRT monitor with base stand */
function RetroComputerIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
      {/* Monitor body */}
      <rect x="2" y="3" width="20" height="14" rx="2" />
      {/* Screen */}
      <rect x="4.5" y="5.5" width="15" height="9" rx="0.5" />
      {/* Stand neck */}
      <line x1="12" y1="17" x2="12" y2="19" />
      {/* Stand base */}
      <line x1="8" y1="19" x2="16" y2="19" />
      {/* Power LED */}
      <circle cx="12" cy="15.5" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Corner-marks expand icon — ┐ top-right + └ bottom-left, diagonal "pull apart" */
function ExpandIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
      {/* Top-right ┐ */}
      <polyline points="9,3 13,3 13,7" />
      {/* Bottom-left └ */}
      <polyline points="7,13 3,13 3,9" />
    </svg>
  );
}

/** Corner-marks collapse icon — ┘ center-left + ┌ center-right, diagonal "push together" */
function CollapseIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={className}>
      {/* Bottom-left pointing inward ┘ */}
      <polyline points="3,10 7,10 7,14" />
      {/* Top-right pointing inward ┌ */}
      <polyline points="13,6 9,6 9,2" />
    </svg>
  );
}

/** Toggle button: icon-only at rest, circular bg + tooltip on hover */
function ToggleButton({ expanded, onClick }: { expanded: boolean; onClick?: () => void }) {
  const [hovered, setHovered] = useState(false);
  const label = expanded ? "收起视窗" : "展开视窗";

  return (
    <div
      className="relative flex items-center justify-center"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Tooltip */}
      {hovered && (
        <div className="absolute bottom-full mb-2 pointer-events-none animate-fade-in">
          <div className="relative bg-[#171717] text-white text-[11px] px-2.5 py-1 rounded-md whitespace-nowrap">
            {label}
            {/* Triangle arrow */}
            <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-[4px] border-l-transparent border-r-[4px] border-r-transparent border-t-[4px] border-t-[#171717]" />
          </div>
        </div>
      )}
      <button
        onClick={onClick}
        className={`w-7 h-7 rounded-full flex items-center justify-center transition-all duration-fast ${
          hovered
            ? "bg-[#f0f0f0] text-[#171717] shadow-[0_0_0_1px_rgba(0,0,0,0.04)]"
            : "text-[#737373]"
        }`}
      >
        {expanded ? (
          <CollapseIcon className="w-3.5 h-3.5" />
        ) : (
          <ExpandIcon className="w-3.5 h-3.5" />
        )}
      </button>
    </div>
  );
}

export default function TaskProgress(props: TaskProgressProps) {
  const { isStreaming, sandboxType, sandboxStatus, computerOpen = false, onToggleComputer } = props;

  return (
    <div className="bg-white">
      <div className="max-w-3xl mx-auto px-4">
        <div className="px-2 py-2">
          <div className="w-full flex items-center gap-3 p-2.5 rounded-lg bg-[#fafafa] border border-[#e5e5e5]">
            <div className="w-7 h-7 rounded-lg bg-[#f5f5f5] flex items-center justify-center flex-shrink-0">
              <RetroComputerIcon className="w-4 h-4 text-[#737373]" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 text-sm">
                <span className="w-2 h-2 rounded-full" style={{ background: statusColor(sandboxStatus) }} />
                <span className="text-[#171717]">
                  {sandboxLabel(sandboxType ?? "local")}
                  {sandboxStatus && (
                    <>
                      {" "}
                      {sandboxStatus === "running" ? "运行中" : sandboxStatus === "paused" ? "已暂停" : sandboxStatus === "detached" ? "已断开" : sandboxStatus}
                    </>
                  )}
                </span>
                <span className="text-[#e5e5e5]">&middot;</span>
                <span className={isStreaming ? "text-[#171717] font-medium" : "text-[#a3a3a3]"}>
                  {isStreaming ? "Mycel 正在工作" : "Mycel 待命中"}
                </span>
              </div>
            </div>
            <ToggleButton expanded={computerOpen} onClick={onToggleComputer} />
          </div>
        </div>
      </div>
    </div>
  );
}
