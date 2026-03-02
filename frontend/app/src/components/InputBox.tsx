import { Paperclip, Send, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

export interface DroppedUploadFile {
  file: File;
  relativePath: string;
}

interface InputBoxProps {
  disabled?: boolean;
  placeholder?: string;
  isStreaming?: boolean;
  onSendMessage: (message: string) => Promise<void> | void;
  onSendQueueMessage?: (message: string) => Promise<void> | void;
  onStop?: () => void;
  onDropUploadFiles?: (files: DroppedUploadFile[]) => Promise<string[]>;
}

export default function InputBox({
  disabled = false,
  placeholder = "告诉 Mycel 你需要什么帮助...",
  isStreaming = false,
  onSendMessage,
  onSendQueueMessage,
  onStop,
  onDropUploadFiles,
}: InputBoxProps) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [dropError, setDropError] = useState<string | null>(null);
  const [uploadingDrop, setUploadingDrop] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const sendingRef = useRef(false);
  const dropRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const autoResize = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  useEffect(() => {
    autoResize();
  }, [value, autoResize]);

  // During streaming, input is enabled for queue messages
  const canSendQueue = isStreaming && !!onSendQueueMessage;
  const inputDisabled = disabled && !canSendQueue;
  const canSend = !!value.trim() && !inputDisabled;
  const showStopButton = isStreaming && !value.trim() && !!onStop;

  async function handleSend() {
    const text = value.trim();
    if (!text || sendingRef.current) return;
    if (canSendQueue) {
      setValue("");
      await onSendQueueMessage!(text);
    } else if (!disabled) {
      sendingRef.current = true;
      setValue("");
      try {
        await onSendMessage(text);
      } finally {
        sendingRef.current = false;
      }
    }
    inputRef.current?.focus();
  }

  function handleStop() {
    if (onStop) {
      onStop();
    }
  }

  type DataTransferItemMaybeWebkit = DataTransferItem & {
    webkitGetAsEntry?: () => FileSystemEntry | null;
  };

  async function readAllDirectoryEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
    const allEntries: FileSystemEntry[] = [];
    while (true) {
      const chunk = await new Promise<FileSystemEntry[]>((resolve, reject) => {
        reader.readEntries(resolve, reject);
      });
      if (chunk.length === 0) break;
      allEntries.push(...chunk);
    }
    return allEntries;
  }

  async function toFile(entry: FileSystemFileEntry): Promise<File> {
    return new Promise<File>((resolve, reject) => {
      entry.file(resolve, reject);
    });
  }

  // @@@drop-folder-traverse - Traverse dropped directory entries recursively so folder drag can preserve relative paths.
  async function collectFromEntry(
    entry: FileSystemEntry,
    parentPath = ""
  ): Promise<DroppedUploadFile[]> {
    if (entry.isFile) {
      const fileEntry = entry as FileSystemFileEntry;
      const file = await toFile(fileEntry);
      const relativePath = parentPath ? `${parentPath}/${file.name}` : file.name;
      return [{ file, relativePath }];
    }
    if (!entry.isDirectory) return [];
    const dirEntry = entry as FileSystemDirectoryEntry;
    const nextPath = parentPath ? `${parentPath}/${dirEntry.name}` : dirEntry.name;
    const reader = dirEntry.createReader();
    const childEntries = await readAllDirectoryEntries(reader);
    const batches = await Promise.all(childEntries.map((child) => collectFromEntry(child, nextPath)));
    return batches.flat();
  }

  async function collectDroppedFiles(event: React.DragEvent<HTMLDivElement>): Promise<DroppedUploadFile[]> {
    const items = Array.from(event.dataTransfer.items);
    if (items.length > 0) {
      const supportsWebkitEntry = items.some((item) => typeof (item as DataTransferItemMaybeWebkit).webkitGetAsEntry === "function");
      if (supportsWebkitEntry) {
        const allBatches = await Promise.all(
          items.map(async (item) => {
            const entry = (item as DataTransferItemMaybeWebkit).webkitGetAsEntry?.();
            if (!entry) return [];
            return collectFromEntry(entry);
          }),
        );
        return allBatches.flat();
      }
    }

    return Array.from(event.dataTransfer.files).map((file) => {
      const relativePath = file.webkitRelativePath?.trim() || file.name;
      return { file, relativePath };
    });
  }

  function hasDraggedFiles(event: React.DragEvent<HTMLDivElement>): boolean {
    return Array.from(event.dataTransfer.types).includes("Files");
  }

  function handleDragOver(event: React.DragEvent<HTMLDivElement>) {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragOver(true);
  }

  function handleDragLeave(event: React.DragEvent<HTMLDivElement>) {
    const current = dropRef.current;
    const related = event.relatedTarget;
    if (current && related instanceof Node && current.contains(related)) return;
    setDragOver(false);
  }

  async function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    if (!hasDraggedFiles(event)) return;
    event.preventDefault();
    setDragOver(false);
    setDropError(null);
    if (!onDropUploadFiles) {
      setDropError("当前线程未启用拖拽上传");
      return;
    }
    const droppedFiles = await collectDroppedFiles(event);
    if (droppedFiles.length === 0) return;
    setUploadingDrop(true);
    try {
      const uploadedPaths = await onDropUploadFiles(droppedFiles);
      const lines = uploadedPaths.map((path) => `- ${path}`);
      const hint = `已上传到 upload 通道：\n${lines.join("\n")}`;
      setValue((prev) => (prev.trim() ? `${prev.trimEnd()}\n\n${hint}` : hint));
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      setDropError(`拖拽上传失败: ${msg}`);
    } finally {
      setUploadingDrop(false);
    }
  }

  async function handleFileInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length === 0) return;
    if (!onDropUploadFiles) return;
    setDropError(null);
    setUploadingDrop(true);
    try {
      const droppedFiles: DroppedUploadFile[] = files.map((f) => ({ file: f, relativePath: f.name }));
      const uploadedPaths = await onDropUploadFiles(droppedFiles);
      const lines = uploadedPaths.map((path) => `- ${path}`);
      const hint = `已上传到 upload 通道：\n${lines.join("\n")}`;
      setValue((prev) => (prev.trim() ? `${prev.trimEnd()}\n\n${hint}` : hint));
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      setDropError(`上传失败: ${msg}`);
    } finally {
      setUploadingDrop(false);
      inputRef.current?.focus();
    }
  }

  return (
    <div className="bg-white pb-4">
      <div className="max-w-3xl mx-auto px-4">
        <div
          ref={dropRef}
          onDragOver={handleDragOver}
          onDragEnter={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={(e) => { void handleDrop(e); }}
          onClick={() => inputRef.current?.focus()}
          className={`flex items-end gap-2 rounded-2xl border transition-all cursor-text ${
            dragOver
              ? "border-[#3b82f6] bg-[#eff6ff]"
              : focused
                ? "border-[#e5e5e5] shadow-sm bg-[#fafafa]"
                : "border-transparent bg-[#fafafa]"
          }`}
        >
          <div className="flex-1 py-4 pl-4">
            <textarea
              ref={inputRef}
              value={value}
              disabled={inputDisabled}
              onChange={(e) => setValue(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
              placeholder={canSendQueue ? "输入消息，将立即插入对话..." : placeholder}
              className="w-full bg-transparent text-sm resize-none outline-none border-none text-[#171717] placeholder:text-[#a3a3a3] disabled:opacity-50"
              rows={1}
              style={{ boxShadow: "none", overflow: "hidden" }}
            />
          </div>
          <div className="flex items-center gap-1 pr-3 py-4">
            {onDropUploadFiles && (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => { void handleFileInputChange(e); }}
                />
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                  disabled={uploadingDrop}
                  title="上传文件"
                  className="w-8 h-8 rounded-full flex items-center justify-center text-[#a3a3a3] hover:text-[#404040] hover:bg-[#f0f0f0] transition-all disabled:opacity-40"
                >
                  <Paperclip className="w-4 h-4" />
                </button>
              </>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (showStopButton) {
                  handleStop();
                } else {
                  void handleSend();
                }
              }}
              disabled={!canSend && !showStopButton}
              className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                showStopButton
                  ? "bg-red-500 text-white hover:bg-red-600"
                  : canSend
                    ? "bg-[#171717] text-white hover:bg-[#404040]"
                    : "bg-[#f5f5f5] text-[#d4d4d4]"
              }`}
            >
              {showStopButton ? <Square className="w-4 h-4" fill="currentColor" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </div>
        {(uploadingDrop || dropError) && (
          <div className="px-1 pt-1">
            {uploadingDrop && <p className="text-[11px] text-[#2563eb]">正在上传...</p>}
            {dropError && <p className="text-[11px] text-red-500">{dropError}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
