import { Paperclip, Send, Square, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

interface InputBoxProps {
  disabled?: boolean;
  placeholder?: string;
  isStreaming?: boolean;
  onSendMessage: (message: string) => Promise<void> | void;
  onSendQueueMessage?: (message: string) => Promise<void> | void;
  onStop?: () => void;
  attachedFiles?: File[];
  onAttachFiles?: (files: File[]) => void;
  onRemoveFile?: (index: number) => void;
}

export default function InputBox({
  disabled = false,
  placeholder = "告诉 Mycel 你需要什么帮助...",
  isStreaming = false,
  onSendMessage,
  onSendQueueMessage,
  onStop,
  attachedFiles = [],
  onAttachFiles,
  onRemoveFile,
}: InputBoxProps) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sendingRef = useRef(false);

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

  return (
    <div className="bg-background pb-4">
      <div className="max-w-3xl mx-auto px-4">
        {attachedFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {attachedFiles.map((file, index) => (
              <div
                key={index}
                className="flex items-center gap-2 px-3 py-2 bg-muted rounded-lg text-sm"
              >
                <span className="text-foreground truncate max-w-[200px]">{file.name}</span>
                {onRemoveFile && (
                  <button
                    type="button"
                    onClick={() => onRemoveFile(index)}
                    className="text-muted-foreground hover:text-foreground transition-colors duration-fast"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        <div
          onClick={() => inputRef.current?.focus()}
          className={`flex items-end gap-2 rounded-2xl border transition-[border-color,box-shadow,background-color] duration-fast cursor-text ${
            focused
              ? "border-border shadow-sm bg-muted"
              : "border-transparent bg-muted"
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
              className="w-full bg-transparent text-sm resize-none outline-none border-none text-foreground placeholder:text-muted-foreground/70 disabled:opacity-50"
              rows={1}
              style={{ boxShadow: "none", overflow: "hidden" }}
            />
          </div>
          <div className="flex items-center pr-3 py-4">
            {onAttachFiles && (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    if (files.length > 0) {
                      onAttachFiles(files);
                    }
                    e.target.value = "";
                  }}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={inputDisabled}
                  className="w-8 h-8 rounded-full flex items-center justify-center transition-colors duration-fast text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50"
                  title="附加文件"
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
              className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors duration-fast ${
                showStopButton
                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  : canSend
                    ? "bg-foreground text-white hover:bg-foreground/80"
                    : "bg-muted text-muted-foreground/30"
              }`}
            >
              {showStopButton ? <Square className="w-4 h-4" fill="currentColor" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
