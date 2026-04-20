import { Bot, FileText } from "lucide-react";
import type { TabType } from "./types";

interface TabBarProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  hasRunningAgents: boolean;
  hasAgents: boolean;
}

const TABS: { key: TabType; label: string; icon: typeof FileText }[] = [
  { key: "files", label: "文件", icon: FileText },
  { key: "agents", label: "Agent", icon: Bot },
];

export function TabBar({ activeTab, onTabChange, hasRunningAgents, hasAgents }: TabBarProps) {
  return (
    <div className="h-10 flex items-center px-2 flex-shrink-0 border-b border-border">
      {TABS.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          onClick={() => onTabChange(key)}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors duration-fast ${
            activeTab === key
              ? "bg-muted text-foreground font-medium"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Icon className="w-4 h-4" />
          <span>{label}</span>
          {key === "agents" && hasRunningAgents && (
            <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
          )}
          {key === "agents" && !hasRunningAgents && hasAgents && (
            <span className="w-1.5 h-1.5 rounded-full bg-success" />
          )}
        </button>
      ))}
    </div>
  );
}
