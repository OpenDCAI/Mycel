import { useCallback, useState } from "react";
import { getWorkspaceDownloadUrl, listWorkspace, readWorkspaceFile } from "../../api";
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
  handleToggleFolder: (fullPath: string) => Promise<void>;
  handleSelectFile: (fullPath: string) => Promise<void>;
  refreshWorkspace: (pathOverride?: string) => Promise<void>;
  downloadFile: (fullPath: string) => void;
}

export function useFileExplorer({ threadId }: UseFileExplorerOptions): FileExplorerResult {
  const [currentPath, setCurrentPath] = useState<string>("");
  const [workspaceRoot, setWorkspaceRoot] = useState<string>("");
  const [treeNodes, setTreeNodes] = useState<TreeNode[]>([]);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [selectedFileContent, setSelectedFileContent] = useState<string>("");
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);

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
      setSelectedFileContent("(Failed to read file)");
    }
  }, [threadId]);

  const downloadFile = useCallback((fullPath: string) => {
    if (!threadId) return;
    const url = getWorkspaceDownloadUrl(threadId, fullPath);
    window.open(url, "_blank", "noopener,noreferrer");
  }, [threadId]);

  return {
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
    downloadFile,
  };
}
