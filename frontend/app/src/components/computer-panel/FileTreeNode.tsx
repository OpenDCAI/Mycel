import { useRef, useState } from "react";
import { ChevronDown, ChevronRight, Download, FileText, Folder, FolderOpen, Loader2, MoreVertical } from "lucide-react";
import type { TreeNode } from "./types";

interface FileTreeNodeProps {
  node: TreeNode;
  depth: number;
  onToggle: (fullPath: string) => void;
  onSelectFile: (fullPath: string) => void;
  onDownloadFile: (fullPath: string) => void;
  selectedFilePath: string | null;
}

export function FileTreeNode({ node, depth, onToggle, onSelectFile, onDownloadFile, selectedFilePath }: FileTreeNodeProps) {
  const isSelected = !node.is_dir && node.fullPath === selectedFilePath;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  return (
    <>
      <div
        className={`group w-full text-left py-1 pr-2 rounded text-[13px] flex items-center gap-1 transition-colors ${
          isSelected
            ? "bg-blue-50 text-blue-700"
            : "text-[#171717] hover:bg-[#f5f5f5]"
        }`}
        style={{ paddingLeft: `${8 + depth * 16}px` }}
      >
        <button
          type="button"
          className="flex-1 flex items-center gap-1 min-w-0"
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
          <span className="flex-1 truncate text-left">{node.name}</span>
          {!node.is_dir && <span className="text-[10px] text-[#d4d4d4] flex-shrink-0">{node.size}</span>}
        </button>

        {/* Three-dot context menu for files */}
        {!node.is_dir && (
          <div className="relative flex-shrink-0" ref={menuRef}>
            <button
              type="button"
              className="w-5 h-5 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-[#e5e5e5] transition-opacity"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(!menuOpen);
              }}
            >
              <MoreVertical className="w-3 h-3 text-[#737373]" />
            </button>
            {menuOpen && (
              <>
                {/* Backdrop to close menu */}
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 top-full z-20 bg-white border border-[#e5e5e5] rounded shadow-lg py-1 min-w-[120px]">
                  <button
                    type="button"
                    className="w-full text-left px-3 py-1.5 text-xs hover:bg-[#f5f5f5] flex items-center gap-2"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      onDownloadFile(node.fullPath);
                    }}
                  >
                    <Download className="w-3 h-3" />
                    Download
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
      {node.is_dir && node.expanded && node.children?.map((child) => (
        <FileTreeNode
          key={child.fullPath}
          node={child}
          depth={depth + 1}
          onToggle={onToggle}
          onSelectFile={onSelectFile}
          onDownloadFile={onDownloadFile}
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
