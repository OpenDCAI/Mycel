import { useCallback, useState } from "react";
import {
  getWorkspaceChannels,
  getWorkspaceDownloadUrl,
  listWorkspace,
  listWorkspaceChannelFiles,
  readWorkspaceFile,
  uploadWorkspaceFile,
} from "../../api";
import type { WorkspaceChannelFileEntry, WorkspaceChannelKind } from "../../api";
import type { TreeNode } from "./types";
import { buildTreeNodes, updateNodeAtPath } from "./utils";

interface UseFileExplorerOptions {
  threadId: string | null;
}

interface FileExplorerResult {
  currentPath: string;
  setCurrentPath: (path: string) => void;
  workspaceRoot: string;
  treeNodes: TreeNode[];
  selectedFilePath: string | null;
  selectedFileContent: string;
  loadingWorkspace: boolean;
  workspaceError: string | null;
  channel: WorkspaceChannelKind;
  channelRootPath: string;
  workspaceId: string | null;
  channelEntries: WorkspaceChannelFileEntry[];
  loadingChannelFiles: boolean;
  uploadingChannelFile: boolean;
  channelError: string | null;
  setChannel: (channel: WorkspaceChannelKind) => void;
  refreshChannelFiles: () => Promise<void>;
  uploadChannelFile: (file: File) => Promise<void>;
  downloadChannelFile: (relativePath: string) => void;
  handleToggleFolder: (fullPath: string) => Promise<void>;
  handleSelectFile: (fullPath: string) => Promise<void>;
  refreshWorkspace: (pathOverride?: string) => Promise<void>;
}

export function useFileExplorer({ threadId }: UseFileExplorerOptions): FileExplorerResult {
  const [currentPath, setCurrentPath] = useState<string>("");
  const [workspaceRoot, setWorkspaceRoot] = useState<string>("");
  const [treeNodes, setTreeNodes] = useState<TreeNode[]>([]);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [selectedFileContent, setSelectedFileContent] = useState<string>("");
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [channel, setChannelState] = useState<WorkspaceChannelKind>("download");
  const [channelRootPath, setChannelRootPath] = useState<string>("");
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [channelEntries, setChannelEntries] = useState<WorkspaceChannelFileEntry[]>([]);
  const [loadingChannelFiles, setLoadingChannelFiles] = useState(false);
  const [uploadingChannelFile, setUploadingChannelFile] = useState(false);
  const [channelError, setChannelError] = useState<string | null>(null);

  const refreshWorkspace = useCallback(async (pathOverride?: string) => {
    if (!threadId) return;
    const target = pathOverride ?? currentPath;
    setLoadingWorkspace(true);
    setWorkspaceError(null);
    try {
      const data = await listWorkspace(threadId, target || undefined);
      setCurrentPath(data.path);
      if (!workspaceRoot) setWorkspaceRoot(data.path);
      setTreeNodes(buildTreeNodes(data.entries, data.path));
    } catch (e) {
      setWorkspaceError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingWorkspace(false);
    }
  }, [threadId, currentPath, workspaceRoot]);

  const handleToggleFolder = useCallback(async (fullPath: string) => {
    if (!threadId) return;

    const findNode = (nodes: TreeNode[]): TreeNode | undefined => {
      for (const n of nodes) {
        if (n.fullPath === fullPath) return n;
        if (n.children) {
          const found = findNode(n.children);
          if (found) return found;
        }
      }
      return undefined;
    };

    const target = findNode(treeNodes);
    if (!target) return;

    if (target.expanded) {
      setTreeNodes((prev) => updateNodeAtPath(prev, fullPath, (n) => ({ ...n, expanded: false })));
      return;
    }

    if (target.children) {
      setTreeNodes((prev) => updateNodeAtPath(prev, fullPath, (n) => ({ ...n, expanded: true })));
      return;
    }

    // Lazy load children
    setTreeNodes((prev) => updateNodeAtPath(prev, fullPath, (n) => ({ ...n, loading: true })));
    try {
      const data = await listWorkspace(threadId, fullPath);
      const children = buildTreeNodes(data.entries, fullPath);
      setTreeNodes((prev) =>
        updateNodeAtPath(prev, fullPath, (n) => ({ ...n, children, expanded: true, loading: false })),
      );
    } catch {
      setTreeNodes((prev) => updateNodeAtPath(prev, fullPath, (n) => ({ ...n, loading: false })));
    }
  }, [threadId, treeNodes]);

  const handleSelectFile = useCallback(async (fullPath: string) => {
    if (!threadId) return;
    setSelectedFilePath(fullPath);
    try {
      const file = await readWorkspaceFile(threadId, fullPath);
      setSelectedFileContent(file.content);
    } catch {
      setSelectedFileContent("(无法读取文件)");
    }
  }, [threadId]);

  const refreshChannelFiles = useCallback(async (channelOverride?: WorkspaceChannelKind) => {
    if (!threadId) return;
    const targetChannel = channelOverride ?? channel;
    setLoadingChannelFiles(true);
    setChannelError(null);
    try {
      const [channels, files] = await Promise.all([
        getWorkspaceChannels(threadId),
        listWorkspaceChannelFiles(threadId, targetChannel),
      ]);
      setChannelRootPath(targetChannel === "upload" ? channels.upload_path : channels.download_path);
      setWorkspaceId(channels.workspace_id ?? null);
      setChannelEntries(files.entries);
    } catch (e) {
      setChannelError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingChannelFiles(false);
    }
  }, [threadId, channel]);

  const setChannel = useCallback((nextChannel: WorkspaceChannelKind) => {
    setChannelState(nextChannel);
    void refreshChannelFiles(nextChannel);
  }, [refreshChannelFiles]);

  const uploadChannelFile = useCallback(async (file: File) => {
    if (!threadId) return;
    setUploadingChannelFile(true);
    setChannelError(null);
    try {
      await uploadWorkspaceFile(threadId, { file, channel });
      await refreshChannelFiles(channel);
    } catch (e) {
      setChannelError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploadingChannelFile(false);
    }
  }, [threadId, channel, refreshChannelFiles]);

  const downloadChannelFile = useCallback((relativePath: string) => {
    if (!threadId) return;
    const url = getWorkspaceDownloadUrl(threadId, relativePath, channel);
    window.open(url, "_blank", "noopener,noreferrer");
  }, [threadId, channel]);

  return {
    currentPath,
    setCurrentPath,
    workspaceRoot,
    treeNodes,
    selectedFilePath,
    selectedFileContent,
    loadingWorkspace,
    workspaceError,
    channel,
    channelRootPath,
    workspaceId,
    channelEntries,
    loadingChannelFiles,
    uploadingChannelFile,
    channelError,
    setChannel,
    refreshChannelFiles: () => refreshChannelFiles(),
    uploadChannelFile,
    downloadChannelFile,
    handleToggleFolder,
    handleSelectFile,
    refreshWorkspace,
  };
}
