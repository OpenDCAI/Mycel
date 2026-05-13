import { useEffect, useMemo, useState } from "react";
import type { ChatEntry } from "../../api";
import type { TabType } from "./types";
import { extractAgentSteps } from "./utils";
import { useRemoteWorkspaceRoot } from "./use-remote-workspace-root";
import { useFileExplorer } from "./use-file-explorer";
import { useResizable } from "./use-resizable";
import { PanelHeader } from "./PanelHeader";
import { TabBar } from "./TabBar";
import { AgentsView } from "./AgentsView";
import { FilesView } from "./FilesView";

interface ComputerPanelProps {
  isOpen: boolean;
  onClose: () => void;
  threadId: string | null;
  sandboxType: string | null;
  chatEntries: ChatEntry[];
  width?: number;
  activeTab?: TabType;
  onTabChange?: (tab: TabType) => void;
}

export default function ComputerPanel({
  isOpen,
  onClose,
  threadId,
  sandboxType,
  chatEntries,
  width = 600,
  activeTab: controlledTab,
  onTabChange,
}: ComputerPanelProps) {
  const [internalTab, setInternalTab] = useState<TabType>("files");
  const activeTab = controlledTab ?? internalTab;
  const setActiveTab = onTabChange ?? setInternalTab;

  const isRemote = sandboxType !== null && sandboxType !== "local";
  const agentSteps = useMemo(() => extractAgentSteps(chatEntries), [chatEntries]);
  const { width: treeWidth, onMouseDown: onDragStart } = useResizable(288, 160, 500);

  const { refreshWorkspaceRoot } = useRemoteWorkspaceRoot({ threadId, isRemote });
  const {
    currentPath,
    setCurrentPath,
    workspaceRoot,
    treeNodes,
    selectedFilePath,
    selectedFileContent,
    loadingWorkspace,
    workspaceError,
    handleToggleFolder,
    handleSelectFile,
    refreshWorkspace,
  } = useFileExplorer({ threadId });

  // Resolve the remote cwd before loading files so the tree opens at the workspace root.
  useEffect(() => {
    if (!isOpen) return;
    refreshWorkspaceRoot().then((cwd) => {
      if (cwd && !currentPath) {
        setCurrentPath(cwd);
      }
    });
  }, [isOpen, refreshWorkspaceRoot, currentPath, setCurrentPath]);

  // Refresh workspace when files tab is active
  useEffect(() => {
    if (!isOpen || !threadId || activeTab !== "files") return;
    void refreshWorkspace();
  }, [isOpen, threadId, activeTab, refreshWorkspace]);

  if (!isOpen) return null;

  return (
    <div
      className="h-full flex flex-col animate-fade-in bg-card border-l border-border flex-shrink-0"
      style={{ width }}
    >
      <PanelHeader
        threadId={threadId}
        onClose={onClose}
      />

      <TabBar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        hasRunningAgents={agentSteps.some((s) => s.status === "calling")}
        hasAgents={agentSteps.length > 0}
      />

      <div className="flex-1 overflow-hidden">
        {activeTab === "agents" && (
          <AgentsView
            steps={agentSteps}
          />
        )}

        {activeTab === "files" && (
          <FilesView
            workspaceRoot={workspaceRoot}
            treeNodes={treeNodes}
            loadingWorkspace={loadingWorkspace}
            workspaceError={workspaceError}
            selectedFilePath={selectedFilePath}
            selectedFileContent={selectedFileContent}
            treeWidth={treeWidth}
            onDragStart={onDragStart}
            onToggleFolder={handleToggleFolder}
            onSelectFile={handleSelectFile}
          />
        )}

      </div>
    </div>
  );
}
