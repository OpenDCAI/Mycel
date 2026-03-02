import type { ChatEntry, LeaseStatus, SessionStatus, TerminalStatus } from "../../api";

export type TabType = "terminal" | "files" | "agents";

export interface ComputerPanelProps {
  isOpen: boolean;
  onClose: () => void;
  threadId: string | null;
  sandboxType: string | null;
  chatEntries: ChatEntry[];
  width?: number;
  activeTab?: TabType;
  onTabChange?: (tab: TabType) => void;
  isStreaming?: boolean;
}

export interface TreeNode {
  name: string;
  fullPath: string;
  is_dir: boolean;
  size: number;
  children_count?: number | null;
  children?: TreeNode[];
  expanded?: boolean;
  loading?: boolean;
}

export interface SandboxStatus {
  session: SessionStatus | null;
  terminal: TerminalStatus | null;
  lease: LeaseStatus | null;
  error: string | null;
  refresh: () => Promise<void>;
}
