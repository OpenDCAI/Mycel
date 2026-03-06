import { Bot, FileText, Terminal, Upload } from "lucide-react";
import type { TabType } from "./types";

interface TabBarProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  hasRunningAgents: boolean;
  hasAgents: boolean;
}

const TABS: { key: TabType; label: string; icon: typeof Terminal }[] = [
  { key: "terminal", label: "终端", icon: Terminal },
  { key: "files", label: "文件", icon: FileText },
  { key: "uploads", label: "Uploads", icon: Upload },
  { key: "agents", label: "助手", icon: Bot },
];

export function TabBar({ activeTab, onTabChange, hasRunningAgents, hasAgents }: TabBarProps) {
  return (
    <div className="h-10 flex items-center px-2 flex-shrink-0 border-b border-[#e5e5e5]">
      {TABS.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          onClick={() => onTabChange(key)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
            activeTab === key
              ? "bg-[#f5f5f5] text-[#171717] font-medium"
              : "text-[#737373] hover:text-[#171717]"
          }`}
        >
          <Icon className="w-4 h-4" />
          <span>{label}</span>
          {key === "agents" && hasRunningAgents && (
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          )}
          {key === "agents" && !hasRunningAgents && hasAgents && (
            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
          )}
        </button>
      ))}
    </div>
  );
}
