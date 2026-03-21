import { ChevronDown, Folder, Send } from "lucide-react";
import { useState } from "react";
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
  defaultWorkspace?: string;
  defaultModel?: string;
  recentWorkspaces?: string[];
  enabledModels?: string[];
  onSend: (message: string, sandbox: string, model: string, workspace?: string) => Promise<void>;
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
  defaultWorkspace,
  defaultModel = "leon:large",
  recentWorkspaces = [],
  enabledModels = [],
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
  const [showCustomModels, setShowCustomModels] = useState(
    () => !MODELS.some((m) => m.value === defaultModel) && !!defaultModel
  );

  const isLocalSandbox = sandbox === "local";

  async function handleSend() {
    const text = message.trim();
    if (!text || sending) return;

    setSending(true);
    try {
      const finalWorkspace = customWorkspace || workspace || undefined;
      await onSend(text, sandbox, model, finalWorkspace);
      setMessage("");
      setCustomWorkspace("");
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

  function persistWorkspace(path: string) {
    return fetch("/api/settings/workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: path }),
    }).catch(() => {});
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

        <div className="flex items-center gap-2 flex-wrap">
          <Select value={sandbox} onValueChange={setSandbox}>
            <SelectTrigger className="w-[140px] h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sandboxTypes.map((type) => (
                <SelectItem key={type.name} value={type.name} disabled={!type.available}>
                  {formatSandboxLabel(type.name)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {isLocalSandbox && (
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

          <Popover open={modelPopoverOpen} onOpenChange={setModelPopoverOpen}>
            <PopoverTrigger asChild>
              <button className="h-9 px-3 text-sm border rounded-md flex items-center gap-2 max-w-[200px] hover:bg-accent">
                <span className="truncate">{MODELS.find((m) => m.value === model)?.label || model}</span>
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
              <div className="border-t my-1" />
              <div className="flex items-center justify-between px-3 py-1.5">
                <span className="text-xs text-muted-foreground">Custom</span>
                <button
                  onClick={() => setShowCustomModels(!showCustomModels)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${showCustomModels ? "bg-primary" : "bg-muted"}`}
                >
                  <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${showCustomModels ? "translate-x-4" : "translate-x-0.5"}`} />
                </button>
              </div>
              {showCustomModels && enabledModels.map((id) => (
                <button
                  key={id}
                  onClick={() => { setModel(id); setModelPopoverOpen(false); }}
                  className={`w-full text-left px-3 py-1.5 text-xs rounded-md truncate ${model === id ? "bg-accent font-medium" : "hover:bg-accent/50"}`}
                >
                  {id}
                </button>
              ))}
            </PopoverContent>
          </Popover>

          <div className="flex-1" />

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
