import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, Loader2 } from "lucide-react";
import type { TreeNode } from "./types";

interface FileTreeNodeProps {
  node: TreeNode;
  depth: number;
  onToggle: (fullPath: string) => void;
  onSelectFile: (fullPath: string) => void;
  selectedFilePath: string | null;
}

export function FileTreeNode({ node, depth, onToggle, onSelectFile, selectedFilePath }: FileTreeNodeProps) {
  const isSelected = !node.is_dir && node.fullPath === selectedFilePath;

  return (
    <>
      <button
        className={`w-full text-left py-1 pr-2 rounded text-[13px] flex items-center gap-1 transition-colors ${
          isSelected
            ? "bg-blue-50 text-blue-700"
            : "text-[#171717] hover:bg-[#f5f5f5]"
        }`}
        style={{ paddingLeft: `${8 + depth * 16}px` }}
        onClick={() => {
          if (node.is_dir) {
            onToggle(node.fullPath);
          } else {
            onSelectFile(node.fullPath);
          }
        }}
      >
        <NodeChevron node={node} />
        <NodeIcon node={node} />
        <span className="flex-1 truncate">{node.name}</span>
        {!node.is_dir && <span className="text-[10px] text-[#d4d4d4] flex-shrink-0">{node.size}</span>}
      </button>
      {node.is_dir && node.expanded && node.children?.map((child) => (
        <FileTreeNode
          key={child.fullPath}
          node={child}
          depth={depth + 1}
          onToggle={onToggle}
          onSelectFile={onSelectFile}
          selectedFilePath={selectedFilePath}
        />
      ))}
    </>
  );
}

function NodeChevron({ node }: { node: TreeNode }) {
  if (!node.is_dir) return <span className="w-3.5 flex-shrink-0" />;
  if (node.loading) return <Loader2 className="w-3.5 h-3.5 animate-spin text-[#a3a3a3] flex-shrink-0" />;
  if (node.expanded) return <ChevronDown className="w-3.5 h-3.5 text-[#a3a3a3] flex-shrink-0" />;
  return <ChevronRight className="w-3.5 h-3.5 text-[#a3a3a3] flex-shrink-0" />;
}

function NodeIcon({ node }: { node: TreeNode }) {
  if (!node.is_dir) return <FileText className="w-4 h-4 text-[#a3a3a3] flex-shrink-0" />;
  if (node.expanded) return <FolderOpen className="w-4 h-4 text-[#525252] flex-shrink-0" />;
  return <Folder className="w-4 h-4 text-[#525252] flex-shrink-0" />;
}
