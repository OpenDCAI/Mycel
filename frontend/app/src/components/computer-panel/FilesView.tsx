import { Loader2 } from "lucide-react";
import type { TreeNode } from "./types";
import { FileTreeNode } from "./FileTreeNode";

interface FilesViewProps {
  workspaceRoot: string;
  treeNodes: TreeNode[];
  loadingWorkspace: boolean;
  workspaceError: string | null;
  selectedFilePath: string | null;
  selectedFileContent: string;
  treeWidth: number;
  onDragStart: (e: React.MouseEvent) => void;
  onToggleFolder: (fullPath: string) => void;
  onSelectFile: (fullPath: string) => void;
}

export function FilesView({
  workspaceRoot,
  treeNodes,
  loadingWorkspace,
  workspaceError,
  selectedFilePath,
  selectedFileContent,
  treeWidth,
  onDragStart,
  onToggleFolder,
  onSelectFile,
}: FilesViewProps) {
  return (
    <div className="h-full flex bg-white">
      {/* File tree -- resizable */}
      <div className="flex flex-col border-r border-[#e5e5e5] flex-shrink-0" style={{ width: treeWidth }}>
        <div className="px-3 py-2 border-b border-[#e5e5e5]">
          <div className="text-xs text-[#737373] font-medium truncate">
            {workspaceRoot ? workspaceRoot.split("/").pop() || "/" : "/"}
          </div>
        </div>
        <div className="flex-1 overflow-auto py-1">
          {loadingWorkspace && (
            <div className="text-xs flex items-center gap-2 px-2 py-2 text-[#737373]">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              加载中...
            </div>
          )}
          {workspaceError && <p className="text-xs px-2 py-2 text-red-500">{workspaceError}</p>}
          {!loadingWorkspace && !workspaceError && treeNodes.map((node) => (
            <FileTreeNode
              key={node.fullPath}
              node={node}
              depth={0}
              onToggle={onToggleFolder}
              onSelectFile={onSelectFile}
              selectedFilePath={selectedFilePath}
            />
          ))}
        </div>
      </div>

      {/* Drag handle */}
      <div
        className="w-1 cursor-col-resize hover:bg-blue-400 active:bg-blue-500 transition-colors duration-fast flex-shrink-0"
        onMouseDown={onDragStart}
      />

      {/* File preview */}
      <div className="flex-1 min-w-0 overflow-auto">
        {!selectedFilePath ? (
          <div className="h-full flex items-center justify-center text-sm text-[#a3a3a3]">
            选择文件以预览
          </div>
        ) : (
          <div className="h-full flex flex-col">
            <div className="px-4 py-2 text-xs font-mono border-b border-[#e5e5e5] text-[#737373]">
              {selectedFilePath}
            </div>
            <pre className="flex-1 p-4 text-sm whitespace-pre-wrap break-words font-mono text-[#404040]">
              {selectedFileContent}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
