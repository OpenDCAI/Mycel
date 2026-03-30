import { Send, Settings2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Button } from "./ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

interface CenteredInputBoxProps {
  defaultModel?: string;
  environmentControl: {
    summary: ReactNode;
    renderPanel: (args: {
      draftModel: string;
      setDraftModel: (value: string) => void;
    }) => ReactNode;
    panelClassName?: string;
    onOpen?: () => void;
    onCancel?: () => void;
    onApply?: (draftModel: string) => boolean | Promise<boolean>;
    onBack?: () => void;
    backLabel?: string;
    showBack?: boolean;
    applyLabel?: string;
    applyDisabled?: boolean;
  };
  onSend: (message: string, model: string) => Promise<void>;
}

const MODEL_LABELS: Record<string, string> = {
  "leon:mini": "Mini",
  "leon:medium": "Medium",
  "leon:large": "Large",
  "leon:max": "Max",
};

export default function CenteredInputBox({
  defaultModel = "leon:large",
  environmentControl,
  onSend,
}: CenteredInputBoxProps) {
  const [message, setMessage] = useState("");
  const [model, setModel] = useState(defaultModel);
  const [draftModel, setDraftModel] = useState(defaultModel);
  const [sending, setSending] = useState(false);
  const [advancedConfigOpen, setAdvancedConfigOpen] = useState(false);
  const [applyingConfig, setApplyingConfig] = useState(false);

  useEffect(() => {
    setModel(defaultModel);
    setDraftModel(defaultModel);
  }, [defaultModel]);

  async function handleSend() {
    const text = message.trim();
    if (!text || sending) return;

    setSending(true);
    try {
      await onSend(text, model);
      setMessage("");
      setAdvancedConfigOpen(false);
    } finally {
      setSending(false);
    }
  }

  function openAdvancedConfig() {
    setDraftModel(model);
    environmentControl.onOpen?.();
    setAdvancedConfigOpen(true);
  }

  function cancelAdvancedConfig() {
    setDraftModel(model);
    environmentControl.onCancel?.();
    setAdvancedConfigOpen(false);
  }

  async function applyAdvancedConfig() {
    setApplyingConfig(true);
    try {
      const shouldClose = (await environmentControl.onApply?.(draftModel)) ?? true;
      if (!shouldClose) return;
      setModel(draftModel);
      setAdvancedConfigOpen(false);
    } finally {
      setApplyingConfig(false);
    }
  }

  const activeModelLabel = MODEL_LABELS[model] ?? model;

  return (
    <div className="w-full max-w-[600px]">
      <div className="rounded-[24px] border border-border bg-card p-6 shadow-lg">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
          placeholder="告诉 Mycel 你需要什么帮助..."
          className="mb-4 w-full resize-none border-none bg-transparent text-base text-foreground outline-none placeholder:text-muted-foreground"
          rows={6}
          disabled={sending}
          style={{ boxShadow: "none" }}
        />
        <p className="mb-4 text-[11px] text-muted-foreground">Enter 发送，Shift + Enter 换行</p>

        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1 text-left">
            <div className="line-clamp-2 break-all text-xs leading-5 text-muted-foreground">
              当前环境：{environmentControl.summary} · {activeModelLabel}
            </div>
          </div>

          <Popover
            open={advancedConfigOpen}
            onOpenChange={(nextOpen) => {
              if (nextOpen) {
                openAdvancedConfig();
              } else {
                cancelAdvancedConfig();
              }
            }}
          >
            {advancedConfigOpen && typeof document !== "undefined" && createPortal(
              <div className="fixed inset-0 z-40 bg-black/50" onClick={cancelAdvancedConfig} />,
              document.body,
            )}
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                className="h-9 gap-2 rounded-full px-3 text-sm text-foreground"
                onClick={(event) => {
                  event.preventDefault();
                  if (advancedConfigOpen) {
                    cancelAdvancedConfig();
                  } else {
                    openAdvancedConfig();
                  }
                }}
              >
                <Settings2 className="h-4 w-4" />
                配置
              </Button>
            </PopoverTrigger>
            <PopoverContent
              side="top"
              align="end"
              sideOffset={12}
              className={`flex w-[680px] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-[24px] border border-border bg-background p-0 shadow-xl ${
                environmentControl.panelClassName ?? "max-h-[calc(100vh-4rem)]"
              }`}
            >
              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
                {environmentControl.renderPanel({ draftModel, setDraftModel })}
              </div>

              <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4">
                <Button type="button" variant="ghost" onClick={cancelAdvancedConfig} disabled={applyingConfig}>
                  取消
                </Button>
                {environmentControl.showBack && environmentControl.onBack && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={environmentControl.onBack}
                    disabled={applyingConfig}
                  >
                    {environmentControl.backLabel ?? "返回上一步"}
                  </Button>
                )}
                <Button type="button" onClick={() => void applyAdvancedConfig()} disabled={applyingConfig || environmentControl.applyDisabled}>
                  {environmentControl.applyLabel ?? "确认"}
                </Button>
              </div>
            </PopoverContent>
          </Popover>

          <Button
            onClick={() => void handleSend()}
            disabled={!message.trim() || sending}
            className="h-9 rounded-lg bg-foreground px-4 text-white hover:bg-foreground/80 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Send className="mr-2 h-4 w-4" />
            发送
          </Button>
        </div>
      </div>
    </div>
  );
}
