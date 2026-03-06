import { useState } from "react";
import { X, Upload, Loader2, CheckCircle2, XCircle } from "lucide-react";

interface FileUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (files: File[]) => Promise<void>;
}

interface FileItem {
  file: File;
  status: "pending" | "uploading" | "success" | "error";
  error?: string;
}

export function FileUploadModal({ isOpen, onClose, onUpload }: FileUploadModalProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [uploading, setUploading] = useState(false);

  if (!isOpen) return null;

  function handleFilesSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files;
    if (!selected) return;
    const items: FileItem[] = Array.from(selected).map(file => ({
      file,
      status: "pending",
    }));
    setFiles(prev => [...prev, ...items]);
    event.target.value = "";
  }

  function removeFile(index: number) {
    setFiles(prev => prev.filter((_, i) => i !== index));
  }

  async function handleUpload() {
    if (files.length === 0) return;
    setUploading(true);
    const filesToUpload = files.filter(f => f.status === "pending").map(f => f.file);
    try {
      await onUpload(filesToUpload);
      setFiles(prev => prev.map(f => f.status === "pending" ? { ...f, status: "success" } : f));
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      setFiles(prev => prev.map(f => f.status === "pending" ? { ...f, status: "error", error: msg } : f));
    } finally {
      setUploading(false);
    }
  }

  function handleClose() {
    if (!uploading) {
      setFiles([]);
      onClose();
    }
  }

  const hasPending = files.some(f => f.status === "pending");
  const allSuccess = files.length > 0 && files.every(f => f.status === "success");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#e5e5e5]">
          <h2 className="text-sm font-medium text-[#171717]">Upload Files</h2>
          <button
            onClick={handleClose}
            disabled={uploading}
            className="w-6 h-6 rounded flex items-center justify-center text-[#737373] hover:text-[#171717] hover:bg-[#f5f5f5] disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-2">
          {files.length === 0 && (
            <div className="text-center py-8 text-sm text-[#a3a3a3]">
              No files selected
            </div>
          )}
          {files.map((item, index) => (
            <div key={index} className="flex items-center gap-2 p-2 rounded border border-[#e5e5e5]">
              <div className="flex-1 min-w-0">
                <div className="text-sm text-[#171717] truncate">{item.file.name}</div>
                <div className="text-xs text-[#737373]">
                  {(item.file.size / 1024).toFixed(1)} KB
                </div>
                {item.error && <div className="text-xs text-red-500 mt-1">{item.error}</div>}
              </div>
              {item.status === "pending" && (
                <button
                  onClick={() => removeFile(index)}
                  disabled={uploading}
                  className="w-6 h-6 rounded flex items-center justify-center text-[#737373] hover:text-red-500 hover:bg-red-50 disabled:opacity-50"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
              {item.status === "uploading" && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
              {item.status === "success" && <CheckCircle2 className="w-4 h-4 text-green-500" />}
              {item.status === "error" && <XCircle className="w-4 h-4 text-red-500" />}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between px-4 py-3 border-t border-[#e5e5e5]">
          <label className="inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded border border-[#d4d4d4] text-[#404040] hover:bg-[#f5f5f5] cursor-pointer">
            <Upload className="w-4 h-4" />
            Add Files
            <input
              type="file"
              multiple
              className="hidden"
              onChange={handleFilesSelected}
            />
          </label>
          <div className="flex items-center gap-2">
            {allSuccess ? (
              <button
                onClick={handleClose}
                className="px-3 py-1.5 text-sm rounded bg-[#171717] text-white hover:bg-[#404040]"
              >
                Done
              </button>
            ) : (
              <>
                <button
                  onClick={handleClose}
                  disabled={uploading}
                  className="px-3 py-1.5 text-sm rounded border border-[#d4d4d4] text-[#404040] hover:bg-[#f5f5f5] disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void handleUpload()}
                  disabled={!hasPending || uploading}
                  className="px-3 py-1.5 text-sm rounded bg-[#171717] text-white hover:bg-[#404040] disabled:opacity-50 inline-flex items-center gap-2"
                >
                  {uploading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Upload
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
