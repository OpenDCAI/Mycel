import { useRef } from "react";
import { Download, Loader2, RefreshCw, Upload } from "lucide-react";
import type { WorkspaceChannelFileEntry, WorkspaceChannelKind } from "../../api";
import type { TreeNode } from "./types";
import { FileTreeNode } from "./FileTreeNode";

interface FilesViewProps {
  workspaceRoot: string;
  treeNodes: TreeNode[];
  loadingWorkspace: boolean;
  workspaceError: string | null;
  selectedFilePath: string | null;
  selectedFileContent: string;
  channel: WorkspaceChannelKind;
  channelRootPath: string;
  workspaceId: string | null;
  channelEntries: WorkspaceChannelFileEntry[];
  loadingChannelFiles: boolean;
  uploadingChannelFile: boolean;
  channelError: string | null;
  treeWidth: number;
  onDragStart: (e: React.MouseEvent) => void;
  onSetChannel: (channel: WorkspaceChannelKind) => void;
  onRefreshChannelFiles: () => void;
  onUploadChannelFile: (file: File) => void;
  onDownloadChannelFile: (relativePath: string) => void;
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
  channel,
  channelRootPath,
  workspaceId,
  channelEntries,
  loadingChannelFiles,
  uploadingChannelFile,
  channelError,
  treeWidth,
  onDragStart,
  onSetChannel,
  onRefreshChannelFiles,
  onUploadChannelFile,
  onDownloadChannelFile,
  onToggleFolder,
  onSelectFile,
}: FilesViewProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function formatBytes(sizeBytes: number): string {
    if (sizeBytes < 1024) return `${sizeBytes} B`;
    if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
    return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatTime(iso: string): string {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString();
  }

  function triggerUploadPicker() {
    fileInputRef.current?.click();
  }

  function handleUploadChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    onUploadChannelFile(file);
    event.target.value = "";
  }

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
        className="w-1 cursor-col-resize hover:bg-blue-400 active:bg-blue-500 transition-colors flex-shrink-0"
        onMouseDown={onDragStart}
      />

      {/* File preview + channel ops */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex-1 overflow-auto">
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

        <div className="border-t border-[#e5e5e5] h-64 flex flex-col">
          <div className="px-3 py-2 border-b border-[#e5e5e5] flex items-center gap-2">
            <select
              className="h-8 px-2 rounded border border-[#d4d4d4] text-xs text-[#404040] bg-white"
              value={channel}
              onChange={(e) => onSetChannel(e.target.value as WorkspaceChannelKind)}
            >
              <option value="download">download</option>
              <option value="upload">upload</option>
            </select>

            <button
              type="button"
              onClick={triggerUploadPicker}
              disabled={uploadingChannelFile}
              className="h-8 px-3 text-xs rounded border border-[#d4d4d4] text-[#404040] hover:bg-[#f5f5f5] disabled:opacity-60 inline-flex items-center gap-1"
            >
              {uploadingChannelFile ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
              <span>{uploadingChannelFile ? "上传中" : "上传文件"}</span>
            </button>

            <button
              type="button"
              onClick={onRefreshChannelFiles}
              disabled={loadingChannelFiles}
              className="h-8 px-2 rounded border border-[#d4d4d4] text-[#404040] hover:bg-[#f5f5f5] disabled:opacity-60"
              title="刷新列表"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingChannelFiles ? "animate-spin" : ""}`} />
            </button>

            <div className="ml-auto flex flex-col items-end min-w-0">
              {workspaceId && (
                <span className="text-[10px] text-blue-500 font-mono truncate max-w-[45%]" title={workspaceId}>
                  ws:{workspaceId.slice(0, 8)}
                </span>
              )}
              <span className="text-[11px] text-[#737373] truncate max-w-[45%]" title={channelRootPath}>
                {channelRootPath || "channel path 未初始化"}
              </span>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleUploadChange}
            />
          </div>

          <div className="flex-1 overflow-auto">
            {channelError && <p className="text-xs px-3 py-2 text-red-500">{channelError}</p>}
            {!channelError && loadingChannelFiles && (
              <div className="text-xs flex items-center gap-2 px-3 py-2 text-[#737373]">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                读取通道文件中...
              </div>
            )}
            {!channelError && !loadingChannelFiles && channelEntries.length === 0 && (
              <div className="text-xs px-3 py-2 text-[#a3a3a3]">当前通道暂无文件</div>
            )}
            {!channelError && !loadingChannelFiles && channelEntries.map((entry) => (
              <div key={entry.relative_path} className="px-3 py-2 border-b border-[#f5f5f5] flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-mono text-[#404040] truncate" title={entry.relative_path}>
                    {entry.relative_path}
                  </div>
                  <div className="text-[11px] text-[#a3a3a3]">
                    {formatBytes(entry.size_bytes)} · {formatTime(entry.updated_at)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onDownloadChannelFile(entry.relative_path)}
                  className="h-7 px-2 rounded border border-[#d4d4d4] text-[#404040] hover:bg-[#f5f5f5] inline-flex items-center gap-1 text-xs"
                >
                  <Download className="w-3.5 h-3.5" />
                  下载
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
