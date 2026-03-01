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

  const { lease, refreshStatus } = useSandboxStatus({ threadId, isRemote });

  const fileExplorer = useFileExplorer({ threadId });

  // Refresh sandbox status when panel opens
  useEffect(() => {
    if (!isOpen) return;
    refreshStatus().then((cwd) => {
      if (cwd && !fileExplorer.currentPath) {
        fileExplorer.setCurrentPath(cwd);
      }
    });
  }, [isOpen, threadId, sandboxType]);

  // Refresh workspace when files tab is active
  useEffect(() => {
    if (!isOpen || !threadId || activeTab !== "files") return;
    void fileExplorer.refreshWorkspace();
    void fileExplorer.refreshChannelFiles();
  }, [isOpen, threadId, activeTab]);

  if (!isOpen) return null;

  return (
    <div
      className="h-full flex flex-col animate-fade-in bg-white border-l border-[#e5e5e5] flex-shrink-0"
      style={{ width }}
    >
      <PanelHeader
        threadId={threadId}
        isRemote={isRemote}
        lease={lease}
        onClose={onClose}
        onRefreshStatus={refreshStatus}
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
            workspaceRoot={fileExplorer.workspaceRoot}
            treeNodes={fileExplorer.treeNodes}
            loadingWorkspace={fileExplorer.loadingWorkspace}
            workspaceError={fileExplorer.workspaceError}
            selectedFilePath={fileExplorer.selectedFilePath}
            selectedFileContent={fileExplorer.selectedFileContent}
            channel={fileExplorer.channel}
            channelRootPath={fileExplorer.channelRootPath}
            workspaceId={fileExplorer.workspaceId}
            channelEntries={fileExplorer.channelEntries}
            loadingChannelFiles={fileExplorer.loadingChannelFiles}
            uploadingChannelFile={fileExplorer.uploadingChannelFile}
            channelError={fileExplorer.channelError}
            treeWidth={treeWidth}
            onDragStart={onDragStart}
            onSetChannel={fileExplorer.setChannel}
            onRefreshChannelFiles={() => void fileExplorer.refreshChannelFiles()}
            onUploadChannelFile={(file) => void fileExplorer.uploadChannelFile(file)}
            onDownloadChannelFile={fileExplorer.downloadChannelFile}
            onToggleFolder={fileExplorer.handleToggleFolder}
            onSelectFile={fileExplorer.handleSelectFile}
          />
        )}
      </div>
    </div>
  );
}
