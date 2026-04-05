import { useEffect, useMemo, useState } from "react";
import type { ComputerPanelProps, TabType } from "./types";
import { extractAgentSteps, extractCommandSteps } from "./utils";
import { useSandboxStatus } from "./use-sandbox-status";
import { useFileExplorer } from "./use-file-explorer";
import { useResizable } from "./use-resizable";
import { PanelHeader } from "./PanelHeader";
import { TabBar } from "./TabBar";
import { TerminalView } from "./TerminalView";
import { AgentsView } from "./AgentsView";
import { FilesView } from "./FilesView";

export type { ComputerPanelProps };

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
  const [internalTab, setInternalTab] = useState<TabType>("terminal");
  const activeTab = controlledTab ?? internalTab;
  const setActiveTab = onTabChange ?? setInternalTab;

  const isRemote = sandboxType !== null && sandboxType !== "local";
  const commandSteps = useMemo(() => extractCommandSteps(chatEntries), [chatEntries]);
  const agentSteps = useMemo(() => extractAgentSteps(chatEntries), [chatEntries]);
  const { width: treeWidth, onMouseDown: onDragStart } = useResizable(288, 160, 500);

  const { refreshStatus } = useSandboxStatus({ threadId, isRemote });
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

  // Refresh sandbox status when panel opens
  useEffect(() => {
    if (!isOpen) return;
    refreshStatus().then((cwd) => {
      if (cwd && !currentPath) {
        setCurrentPath(cwd);
      }
    });
  }, [isOpen, refreshStatus, currentPath, setCurrentPath]);

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
        {activeTab === "terminal" && <TerminalView steps={commandSteps} />}

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
