import { Send, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

interface InputBoxProps {
  disabled?: boolean;
  placeholder?: string;
  isStreaming?: boolean;
  onSendMessage: (message: string) => Promise<void> | void;
  onSendQueueMessage?: (message: string) => Promise<void> | void;
  onStop?: () => void;
}

export default function InputBox({
  disabled = false,
  placeholder = "告诉 Mycel 你需要什么帮助...",
  isStreaming = false,
  onSendMessage,
  onSendQueueMessage,
  onStop,
}: InputBoxProps) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
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
    <div className="bg-white pb-4">
      <div className="max-w-3xl mx-auto px-4">
        <div
          onClick={() => inputRef.current?.focus()}
          className={`flex items-end gap-2 rounded-2xl border transition-all cursor-text ${
            focused
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
          <div className="flex items-center pr-3 py-4">
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
      </div>
    </div>
  );
}
