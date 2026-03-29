import { ChevronDown, Folder, Send } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { SandboxType } from "../api";
import { Button } from "./ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./ui/popover";
import { Input } from "./ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import FilesystemBrowser from "./FilesystemBrowser";

interface CenteredInputBoxProps {
  sandboxTypes: SandboxType[];
  defaultSandbox?: string;
  sandboxChoices?: Array<{ value: string; label: string; available?: boolean }>;
  hideSandboxSelector?: boolean;
  defaultWorkspace?: string;
  workspaceSelectionEnabled?: boolean;
  defaultModel?: string;
  recentWorkspaces?: string[];
  environmentControl?: {
    renderSummary: (args: EnvironmentControlArgs) => ReactNode;
    renderPanel: (args: EnvironmentControlArgs) => ReactNode;
    isDetailView?: boolean;
    panelClassName?: string;
    onOpen?: () => void;
    onCancel?: () => void;
    onApply?: () => boolean | Promise<boolean>;
    applyLabel?: string;
  };
  onSend: (message: string, sandbox: string, model: string, workspace?: string) => Promise<void>;
}

interface EnvironmentControlArgs {
  sandbox: string;
  setSandbox: (value: string) => void;
  workspace: string;
  setWorkspace: (value: string) => void;
  customWorkspace: string;
  setCustomWorkspace: (value: string) => void;
  persistWorkspace: (path: string) => Promise<void>;
}

const MODELS = [
  { value: "leon:mini", label: "Mini" },
  { value: "leon:medium", label: "Medium" },
  { value: "leon:large", label: "Large" },
  { value: "leon:max", label: "Max" },
];

const SANDBOX_LABELS: Record<string, string> = {
  local: "本地",
  agentbay: "AgentBay",
  daytona: "Daytona",
  docker: "Docker",
  e2b: "E2B",
};

function formatSandboxLabel(name: string): string {
  const known = SANDBOX_LABELS[name];
  if (known) return known;
  // @@@sandbox-label-humanize - Keep /app selector readable when provider name is snake_case (e.g. daytona_selfhost).
  return name
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function CenteredInputBox({
  sandboxTypes,
  defaultSandbox = "local",
  sandboxChoices,
  hideSandboxSelector = false,
  defaultWorkspace,
  workspaceSelectionEnabled = true,
  defaultModel = "leon:large",
  recentWorkspaces = [],
  environmentControl,
  onSend,
}: CenteredInputBoxProps) {
  const [message, setMessage] = useState("");
  const [sandbox, setSandbox] = useState(defaultSandbox);
  const [model, setModel] = useState(defaultModel);
  const [workspace, setWorkspace] = useState(defaultWorkspace || "");
  const [customWorkspace, setCustomWorkspace] = useState("");
  const [sending, setSending] = useState(false);
  const [workspacePopoverOpen, setWorkspacePopoverOpen] = useState(false);
  const [modelPopoverOpen, setModelPopoverOpen] = useState(false);
  const [advancedConfigOpen, setAdvancedConfigOpen] = useState(false);
  const [draftModel, setDraftModel] = useState(defaultModel);
  const [applyingConfig, setApplyingConfig] = useState(false);

  useEffect(() => {
    setSandbox(defaultSandbox);
  }, [defaultSandbox]);

  useEffect(() => {
    setWorkspace(defaultWorkspace || "");
  }, [defaultWorkspace]);

  useEffect(() => {
    setModel(defaultModel);
    setDraftModel(defaultModel);
  }, [defaultModel]);

  const isLocalSandbox = sandbox === "local";
  const choices = sandboxChoices ?? sandboxTypes.map((type) => ({
    value: type.name,
    label: formatSandboxLabel(type.name),
    available: type.available,
  }));

  async function handleSend() {
    const text = message.trim();
    if (!text || sending) return;

    setSending(true);
    try {
      const finalWorkspace = customWorkspace || workspace || undefined;
      await onSend(text, sandbox, model, finalWorkspace);
      setMessage("");
      setCustomWorkspace("");
      setAdvancedConfigOpen(false);
    } finally {
      setSending(false);
    }
  }

  function handleSelectWorkspace(path: string) {
    setWorkspace(path);
    setCustomWorkspace("");
    void persistWorkspace(path);
  }

  function handleBrowserSelect(path: string) {
    setWorkspace(path);
    setCustomWorkspace("");
    setWorkspacePopoverOpen(false);
    void persistWorkspace(path);
  }

  function handleCustomWorkspace() {
    if (customWorkspace.trim()) {
      const path = customWorkspace.trim();
      setWorkspace(path);
      setWorkspacePopoverOpen(false);
      void persistWorkspace(path);
    }
  }

  async function persistWorkspace(path: string): Promise<void> {
    try {
      await fetch("/api/settings/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace: path }),
      });
    } catch {
      // @@@workspace-persist-best-effort - input should still move forward even if the settings write fails.
    }
  }

  const environmentArgs: EnvironmentControlArgs = {
    sandbox,
    setSandbox,
    workspace,
    setWorkspace,
    customWorkspace,
    setCustomWorkspace,
    persistWorkspace,
  };
  const activeModelLabel = MODELS.find((entry) => entry.value === model)?.label ?? model;
  const quietSummary = environmentControl
    ? `${environmentControl.renderSummary(environmentArgs)} · ${activeModelLabel}`
    : activeModelLabel;

  function openAdvancedConfig() {
    setDraftModel(model);
    environmentControl?.onOpen?.();
    setAdvancedConfigOpen(true);
  }

  function cancelAdvancedConfig() {
    setDraftModel(model);
    environmentControl?.onCancel?.();
    setAdvancedConfigOpen(false);
  }

  async function applyAdvancedConfig() {
    setApplyingConfig(true);
    try {
      const shouldClose = (await environmentControl?.onApply?.()) ?? true;
      if (!shouldClose) return;
      setModel(draftModel);
      setAdvancedConfigOpen(false);
    } finally {
      setApplyingConfig(false);
    }
  }

  // ============================================================
  // IMPORTANT: DO NOT remove or truncate the return statement below!
  // This component must return complete JSX with proper closing tags.
  // ====================================================
  return (
    <div className="w-full max-w-[600px]">
      <div className="bg-card rounded-[24px] border border-border shadow-lg p-6">
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
          className="w-full bg-transparent text-base resize-none outline-none border-none text-foreground placeholder:text-muted-foreground mb-4"
          rows={6}
          disabled={sending}
          style={{ boxShadow: "none" }}
        />
        <p className="text-[11px] text-[#a3a3a3] mb-4">Enter 发送，Shift + Enter 换行</p>

        <div className="flex items-center gap-3 min-w-0">
          {environmentControl ? (
            <div className="min-w-0 flex-1 text-left">
              <div className="truncate text-xs text-muted-foreground">
                当前环境：{quietSummary}
              </div>
            </div>
          ) : !hideSandboxSelector && (
            <Select value={sandbox} onValueChange={setSandbox}>
              <SelectTrigger className="w-[170px] h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {choices.map((choice) => (
                  <SelectItem key={choice.value} value={choice.value} disabled={choice.available === false}>
                    {choice.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {workspaceSelectionEnabled && isLocalSandbox && (
            <Popover open={workspacePopoverOpen} onOpenChange={setWorkspacePopoverOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-9 w-9"
                  title={workspace || "选择工作区"}
                >
                  <Folder className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[480px]" align="start">
                <Tabs defaultValue="browse" className="w-full">
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="browse">浏览</TabsTrigger>
                    <TabsTrigger value="recent">最近</TabsTrigger>
                    <TabsTrigger value="manual">手动</TabsTrigger>
                  </TabsList>

                  <TabsContent value="browse" className="space-y-3 mt-3">
                    <FilesystemBrowser
                      onSelect={handleBrowserSelect}
                      initialPath={workspace || "~"}
                    />
                  </TabsContent>

                  <TabsContent value="recent" className="space-y-3 mt-3">
                    {workspace && (
                      <div className="text-xs text-muted-foreground mb-2">
                        当前: {workspace}
                      </div>
                    )}
                    {recentWorkspaces.length > 0 ? (
                      <div className="space-y-1">
                        {recentWorkspaces.map((path) => (
                          <button
                            key={path}
                            onClick={() => handleSelectWorkspace(path)}
                            className="w-full text-left px-2 py-1.5 text-sm hover:bg-accent rounded-md truncate"
                          >
                            {path}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="text-sm text-muted-foreground text-center py-4">
                        暂无最近使用的工作区
                      </div>
                    )}
                  </TabsContent>

                  <TabsContent value="manual" className="space-y-3 mt-3">
                    <div className="space-y-2">
                      <p className="text-xs text-muted-foreground">自定义路径</p>
                      <div className="flex gap-2">
                        <Input
                          value={customWorkspace}
                          onChange={(e) => setCustomWorkspace(e.target.value)}
                          placeholder="例如: ~/Projects"
                          className="flex-1 h-8 text-sm"
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              handleCustomWorkspace();
                            }
                          }}
                        />
                        <Button
                          size="sm"
                          onClick={handleCustomWorkspace}
                          disabled={!customWorkspace.trim()}
                        >
                          确定
                        </Button>
                      </div>
                    </div>
                  </TabsContent>
                </Tabs>
              </PopoverContent>
            </Popover>
          )}

          {!environmentControl && (
            <Popover open={modelPopoverOpen} onOpenChange={setModelPopoverOpen}>
              <PopoverTrigger asChild>
                <button className="h-9 px-3 text-sm border rounded-md flex items-center gap-2 max-w-[200px] hover:bg-accent">
                  <span className="truncate">{activeModelLabel}</span>
                  <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
                </button>
              </PopoverTrigger>
              <PopoverContent className="w-[180px] p-1" align="start">
                {MODELS.map((m) => (
                  <button
                    key={m.value}
                    onClick={() => { setModel(m.value); setModelPopoverOpen(false); }}
                    className={`w-full text-left px-3 py-1.5 text-sm rounded-md ${model === m.value ? "bg-accent font-medium" : "hover:bg-accent/50"}`}
                  >
                    {m.label}
                  </button>
                ))}
              </PopoverContent>
            </Popover>
          )}

          {!environmentControl && <div className="flex-1 min-w-0" />}

          {environmentControl && (
            <Popover
              open={advancedConfigOpen}
              onOpenChange={(nextOpen) => {
                if (nextOpen) {
                  openAdvancedConfig();
                  return;
                }
                cancelAdvancedConfig();
              }}
            >
              {advancedConfigOpen && typeof document !== "undefined" && createPortal(
                <div
                  className="fixed inset-0 z-40 bg-black/50"
                  onClick={cancelAdvancedConfig}
                />,
                document.body,
              )}
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  className="h-9 px-3 text-sm text-muted-foreground hover:text-foreground"
                  onClick={(event) => {
                    event.preventDefault();
                    if (advancedConfigOpen) {
                      cancelAdvancedConfig();
                    } else {
                      openAdvancedConfig();
                    }
                  }}
                >
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
                  {!environmentControl.isDetailView && (
                    <div className="mb-6 space-y-3">
                      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Model</div>
                      <div className="flex flex-wrap gap-2">
                        {MODELS.map((entry) => (
                          <button
                            key={entry.value}
                            type="button"
                            onClick={() => setDraftModel(entry.value)}
                            className={`rounded-xl border px-3 py-2 text-sm transition-colors ${
                              draftModel === entry.value
                                ? "border-foreground bg-foreground text-background"
                                : "border-border bg-card text-foreground hover:bg-accent"
                            }`}
                          >
                            {entry.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {environmentControl.renderPanel(environmentArgs)}
                </div>

                <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4">
                  <Button type="button" variant="ghost" onClick={cancelAdvancedConfig} disabled={applyingConfig}>
                    取消
                  </Button>
                  <Button type="button" onClick={() => void applyAdvancedConfig()} disabled={applyingConfig}>
                    {environmentControl.applyLabel ?? "确认"}
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
          )}

          <Button
            onClick={() => void handleSend()}
            disabled={!message.trim() || sending}
            className="h-9 px-4 bg-foreground text-white hover:bg-foreground/80 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4 mr-2" />
            发送
          </Button>
        </div>
      </div>
    </div>
  );
  // ============================================================
  // END OF COMPONENT - All JSX tags properly closed above
  // ============================================================
}
