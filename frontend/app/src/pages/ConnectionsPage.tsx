import { useState, useEffect, useCallback, useRef } from "react";
import { Plug, QrCode, Loader2, CheckCircle2, XCircle, MessageCircle, Settings, X, ArrowRight } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { request } from "@/api/client";
import MemberAvatar from "@/components/MemberAvatar";
import { toast } from "sonner";

// --- Types ---

interface RoutingConfig {
  type?: "thread" | "chat";
  id?: string;
  label?: string;
}

interface WeChatState {
  connected: boolean;
  polling?: boolean;
  account_id?: string;
  user_id?: string;
  contacts?: { user_id: string; display_name: string }[];
  routing?: RoutingConfig;
}

interface RoutingTarget {
  id: string;
  label: string;
  avatar_url?: string;
}

interface RoutingTargets {
  threads: RoutingTarget[];
  chats: RoutingTarget[];
}

// --- Main Page ---

export default function ConnectionsPage() {
  return (
    <div className="h-full flex flex-col bg-background">
      <div className="h-14 flex items-center px-4 md:px-6 border-b border-border shrink-0">
        <Plug className="w-4 h-4 text-muted-foreground mr-2" />
        <h2 className="text-sm font-semibold text-foreground">Connections</h2>
      </div>
      <div className="flex-1 overflow-auto p-4 md:p-6">
        <div className="max-w-2xl mx-auto space-y-4">
          <WeChatCard />
        </div>
      </div>
    </div>
  );
}

// --- WeChat Connection Card ---

type WeChatPhase = "idle" | "loading-qr" | "showing-qr" | "connected";

function WeChatCard() {
  const [phase, setPhase] = useState<WeChatPhase>("idle");
  const [state, setState] = useState<WeChatState | null>(null);
  const [qrImgUrl, setQrImgUrl] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<string>("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const pollRef = useRef(false);

  // Fetch current state on mount
  useEffect(() => {
    request<WeChatState>("/api/connections/wechat/state").then((s) => {
      setState(s);
      if (s.connected) setPhase("connected");
    }).catch((e) => console.error("WeChat state fetch failed:", e));
  }, []);

  // Refresh state periodically when connected
  useEffect(() => {
    if (phase !== "connected") return;
    const interval = setInterval(() => {
      request<WeChatState>("/api/connections/wechat/state").then(setState).catch((e) => console.error("WeChat state fetch failed:", e));
    }, 10000);
    return () => clearInterval(interval);
  }, [phase]);

  const startConnect = useCallback(async () => {
    setPhase("loading-qr");
    try {
      const data = await request<{ qrcode: string; qrcode_img_url: string }>(
        "/api/connections/wechat/qrcode",
        { method: "POST" },
      );
      setQrImgUrl(data.qrcode_img_url);
      setPhase("showing-qr");
      setScanStatus("等待扫码...");
      pollRef.current = true;
      pollQrStatus(data.qrcode);
    } catch (err) {
      toast.error(`Failed: ${err instanceof Error ? err.message : "unknown"}`);
      setPhase("idle");
    }
  }, []);

  const pollQrStatus = useCallback(async (qr: string) => {
    while (pollRef.current) {
      try {
        const result = await request<{ status: string; account_id?: string }>(
          "/api/connections/wechat/qrcode/poll",
          { method: "POST", body: JSON.stringify({ qrcode: qr }) },
        );
        if (!pollRef.current) return;
        switch (result.status) {
          case "scaned":
            setScanStatus("已扫码，请在微信中确认...");
            break;
          case "confirmed":
            setScanStatus("");
            setPhase("connected");
            pollRef.current = false;
            request<WeChatState>("/api/connections/wechat/state").then(setState);
            toast.success("WeChat connected");
            return;
          case "expired":
            setScanStatus("二维码已过期");
            setPhase("idle");
            pollRef.current = false;
            return;
          case "error":
            setScanStatus("连接失败");
            setPhase("idle");
            pollRef.current = false;
            return;
          default:
            break;
        }
      } catch {
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
  }, []);

  const handleDisconnect = useCallback(async () => {
    pollRef.current = false;
    try {
      await request("/api/connections/wechat/disconnect", { method: "POST" });
      setState(null);
      setPhase("idle");
      setQrImgUrl(null);
      toast.success("WeChat disconnected");
    } catch (err) {
      toast.error(`Disconnect failed: ${err instanceof Error ? err.message : "unknown"}`);
    }
  }, []);

  useEffect(() => () => { pollRef.current = false; }, []);

  const routing = state?.routing;
  const hasRouting = routing?.type && routing?.id;

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Card header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-success/10 flex items-center justify-center">
            <MessageCircle className="w-5 h-5 text-success" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground">WeChat</h3>
            <p className="text-xs text-muted-foreground">连接微信，让 Agent 收发消息</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {phase === "connected" && (
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors duration-fast"
              title="Message routing settings"
            >
              <Settings className="w-4 h-4" />
            </button>
          )}
          <StatusBadge phase={phase} />
        </div>
      </div>

      {/* Card body */}
      <div className="px-5 py-4">
        {phase === "idle" && (
          <button
            onClick={startConnect}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity duration-fast"
          >
            <QrCode className="w-4 h-4" />
            扫码连接
          </button>
        )}

        {phase === "loading-qr" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            获取二维码中...
          </div>
        )}

        {phase === "showing-qr" && qrImgUrl && (
          <div className="space-y-3">
            <div className="flex justify-center">
              <div className="p-4 bg-background rounded-xl">
                <QRCodeSVG value={qrImgUrl} size={192} level="M" />
              </div>
            </div>
            <p className="text-center text-xs text-muted-foreground">{scanStatus}</p>
            <button
              onClick={() => { pollRef.current = false; setPhase("idle"); }}
              className="block mx-auto text-xs text-muted-foreground hover:text-foreground transition-colors duration-fast"
            >
              取消
            </button>
          </div>
        )}

        {phase === "connected" && state && (
          <div className="space-y-4">
            {/* Routing indicator */}
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">消息发送至</span>
              {hasRouting ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-primary/10 text-primary text-xs font-medium">
                  {routing!.type === "thread" ? "会话" : "聊天"}：{routing!.label || routing!.id?.slice(0, 12)}
                </span>
              ) : (
                <button
                  onClick={() => setSettingsOpen(true)}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-warning/10 text-warning text-xs font-medium hover:bg-warning/20 transition-colors duration-fast"
                >
                  未配置 — 点击设置
                </button>
              )}
            </div>

            <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
              <div className="text-muted-foreground">账号</div>
              <div className="font-mono text-xs text-foreground truncate">{state.account_id}</div>
              <div className="text-muted-foreground">轮询</div>
              <div className="text-foreground">{state.polling ? "运行中" : "已停止"}</div>
              <div className="text-muted-foreground">联系人</div>
              <div className="text-foreground">{state.contacts?.length || 0} 个</div>
            </div>

            {state.contacts && state.contacts.length > 0 && (
              <div className="pt-2 border-t border-border">
                <p className="text-xs text-muted-foreground mb-2">最近联系人</p>
                <div className="space-y-1">
                  {state.contacts.map((c) => (
                    <div key={c.user_id} className="flex items-center gap-2 text-xs">
                      <div className="w-5 h-5 rounded-full bg-muted flex items-center justify-center text-2xs font-medium">
                        {c.display_name[0]?.toUpperCase()}
                      </div>
                      <span className="text-foreground">{c.display_name}</span>
                      <span className="text-muted-foreground font-mono truncate">{c.user_id}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button
              onClick={handleDisconnect}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-destructive hover:bg-destructive/10 transition-colors duration-fast"
            >
              <XCircle className="w-3.5 h-3.5" />
              断开连接
            </button>
          </div>
        )}
      </div>

      {/* Settings dialog */}
      {settingsOpen && (
        <RoutingDialog
          currentRouting={routing || {}}
          onClose={() => setSettingsOpen(false)}
          onSaved={(newRouting) => {
            setState((s) => s ? { ...s, routing: newRouting } : s);
            setSettingsOpen(false);
          }}
        />
      )}
    </div>
  );
}

// --- Routing Settings Dialog ---

function RoutingDialog({
  currentRouting,
  onClose,
  onSaved,
}: {
  currentRouting: RoutingConfig;
  onClose: () => void;
  onSaved: (r: RoutingConfig) => void;
}) {
  const [targets, setTargets] = useState<RoutingTargets | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"thread" | "chat">(currentRouting.type || "thread");
  const [selectedId, setSelectedId] = useState<string>(currentRouting.id || "");

  useEffect(() => {
    request<RoutingTargets>("/api/connections/wechat/routing/targets")
      .then(setTargets)
      .catch((e) => toast.error(`Failed to load targets: ${e.message}`))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    if (!selectedId) return;
    const items = tab === "thread" ? targets?.threads : targets?.chats;
    const item = items?.find((t) => t.id === selectedId);
    try {
      await request("/api/connections/wechat/routing", {
        method: "POST",
        body: JSON.stringify({ type: tab, id: selectedId, label: item?.label || "" }),
      });
      onSaved({ type: tab, id: selectedId, label: item?.label || "" });
      toast.success("路由已保存");
    } catch (e) {
      toast.error(`Failed: ${e instanceof Error ? e.message : "unknown"}`);
    }
  };

  const handleClear = async () => {
    try {
      await request("/api/connections/wechat/routing", { method: "DELETE" });
      onSaved({});
      toast.success("路由已清除");
    } catch (e) {
      toast.error(`Failed: ${e instanceof Error ? e.message : "unknown"}`);
    }
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div className="bg-card border border-border rounded-xl shadow-xl w-full max-w-md max-h-[80vh] flex flex-col pointer-events-auto">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
            <h3 className="text-sm font-semibold text-foreground">消息路由</h3>
            <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors duration-fast">
              <X className="w-4 h-4 text-muted-foreground" />
            </button>
          </div>

          {/* Tab selector */}
          <div className="px-5 pt-4 shrink-0">
            <p className="text-xs text-muted-foreground mb-3">
              选择微信消息的接收目标
            </p>
            <div className="flex gap-1 p-0.5 bg-muted rounded-lg">
              <button
                onClick={() => { setTab("thread"); setSelectedId(""); }}
                className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors duration-fast ${
                  tab === "thread" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"
                }`}
              >
                会话
              </button>
              <button
                onClick={() => { setTab("chat"); setSelectedId(""); }}
                className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors duration-fast ${
                  tab === "chat" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"
                }`}
              >
                聊天
              </button>
            </div>
          </div>

          {/* List */}
          <div className="flex-1 overflow-auto px-5 py-3">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
                <Loader2 className="w-4 h-4 animate-spin" />
                加载中...
              </div>
            ) : (
              <ItemList
                items={(tab === "thread" ? targets?.threads : targets?.chats) || []}
                selectedId={selectedId}
                onSelect={setSelectedId}
                emptyText={tab === "thread" ? "暂无会话" : "暂无聊天"}
              />
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-5 py-3 border-t border-border shrink-0">
            <button
              onClick={handleClear}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors duration-fast"
            >
              清除路由
            </button>
            <button
              onClick={handleSave}
              disabled={!selectedId}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 disabled:opacity-40 transition-opacity duration-fast"
            >
              保存
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function ItemList({
  items,
  selectedId,
  onSelect,
  emptyText,
}: {
  items: RoutingTarget[];
  selectedId: string;
  onSelect: (id: string) => void;
  emptyText: string;
}) {
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground text-center py-8">{emptyText}</p>;
  }
  return (
    <div className="space-y-1">
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect(item.id)}
          className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors duration-fast ${
            selectedId === item.id
              ? "bg-primary/10 ring-1 ring-primary/30"
              : "hover:bg-muted"
          }`}
        >
          <MemberAvatar name={item.label} avatarUrl={item.avatar_url} size="sm" type="mycel_agent" />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-foreground truncate">{item.label}</p>
            <p className="text-2xs text-muted-foreground font-mono truncate">{item.id}</p>
          </div>
          {selectedId === item.id && (
            <CheckCircle2 className="w-4 h-4 text-primary shrink-0" />
          )}
        </button>
      ))}
    </div>
  );
}

function StatusBadge({ phase }: { phase: WeChatPhase }) {
  if (phase === "connected") {
    return (
      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-success/10 text-success">
        <CheckCircle2 className="w-3 h-3" />
        已连接
      </span>
    );
  }
  if (phase === "showing-qr" || phase === "loading-qr") {
    return (
      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-warning/10 text-warning">
        <Loader2 className="w-3 h-3 animate-spin" />
        连接中
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-muted text-muted-foreground">
      Not connected
    </span>
  );
}
