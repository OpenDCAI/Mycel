import { useState, useEffect, useCallback } from "react";
import { Download, Loader2, RefreshCw, Upload } from "lucide-react";
import { listWorkspaceChannelFiles, getWorkspaceDownloadUrl } from "../../api";
import type { WorkspaceChannelFileEntry } from "../../api";

interface UploadedFilesViewProps {
  threadId: string;
}

export function UploadedFilesView({ threadId }: UploadedFilesViewProps) {
  const [files, setFiles] = useState<WorkspaceChannelFileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listWorkspaceChannelFiles(threadId, "upload");
      setFiles(result.entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [threadId]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles]);

  function handleDownload(relativePath: string) {
    const url = getWorkspaceDownloadUrl(threadId, relativePath, "upload");
    window.open(url, "_blank", "noopener,noreferrer");
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatTime(iso: string): string {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString();
  }

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="px-3 py-2 border-b border-[#e5e5e5] flex items-center justify-between">
        <div className="text-xs font-medium text-[#171717]">Uploaded Files</div>
        <button
          onClick={() => void loadFiles()}
          disabled={loading}
          className="w-7 h-7 rounded flex items-center justify-center text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5] disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="flex-1 overflow-auto">
        {error && (
          <div className="px-3 py-2 text-xs text-red-500">{error}</div>
        )}
        {!error && loading && (
          <div className="flex items-center gap-2 px-3 py-2 text-xs text-[#737373]">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Loading files...
          </div>
        )}
        {!error && !loading && files.length === 0 && (
          <div className="px-3 py-12 text-center">
            <Upload className="w-12 h-12 mx-auto mb-3 text-[#d4d4d4]" />
            <div className="text-sm text-[#a3a3a3] mb-1">No files uploaded yet</div>
            <div className="text-xs text-[#d4d4d4]">
              Use the paperclip button in the chat input to upload files
            </div>
          </div>
        )}
        {!error && !loading && files.map((file) => (
          <div
            key={file.relative_path}
            className="px-3 py-2 border-b border-[#f5f5f5] hover:bg-[#fafafa] flex items-center gap-2"
          >
            <div className="flex-1 min-w-0">
              <div className="text-sm text-[#171717] truncate" title={file.relative_path}>
                {file.relative_path}
              </div>
              <div className="text-xs text-[#737373]">
                {formatBytes(file.size_bytes)} · {formatTime(file.updated_at)}
              </div>
            </div>
            <button
              onClick={() => handleDownload(file.relative_path)}
              className="w-7 h-7 rounded flex items-center justify-center text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5]"
              title="Download"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
