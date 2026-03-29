import type { ChatEntry, LeaseStatus, SessionStatus, TerminalStatus } from "../../api";
import type { SandboxChannelFileEntry, SandboxChannelKind } from "../../api";

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

export interface FileExplorerState {
  currentPath: string;
  workspaceRoot: string;
  treeNodes: TreeNode[];
  selectedFilePath: string | null;
  selectedFileContent: string;
  loadingWorkspace: boolean;
  workspaceError: string | null;
  channel: SandboxChannelKind;
  channelRootPath: string;
  sandboxFilesId: string | null;
  channelEntries: SandboxChannelFileEntry[];
  loadingChannelFiles: boolean;
  uploadingChannelFile: boolean;
  channelError: string | null;
  setChannel: (channel: SandboxChannelKind) => void;
  refreshChannelFiles: () => Promise<void>;
  uploadChannelFile: (file: File) => Promise<void>;
  downloadChannelFile: (relativePath: string) => void;
  handleToggleFolder: (fullPath: string) => Promise<void>;
  handleSelectFile: (fullPath: string) => Promise<void>;
  refreshWorkspace: (pathOverride?: string) => Promise<void>;
}
