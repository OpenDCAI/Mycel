import { useState, useEffect, useCallback, useRef } from "react";
import { Ticket, Plus, Trash2, Copy, Check, AlertTriangle, RefreshCw, TicketX } from "lucide-react";
import { fetchInviteCodes, generateInviteCode, revokeInviteCode } from "@/api/client";
import type { InviteCode } from "@/api/client";
import { toast } from "sonner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function StatusBadge({ code }: { code: InviteCode }) {
  if (code.used) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground">
        已使用
      </span>
    );
  }
  if (code.expires_at && new Date(code.expires_at) < new Date()) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-warning/10 text-warning">
        已过期
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-success/10 text-success">
      <span className="w-1.5 h-1.5 rounded-full bg-success" />
      未使用
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("已复制到剪贴板");
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("复制失败");
    }
  }, [text]);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={handleCopy}
          className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors duration-fast"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </TooltipTrigger>
      <TooltipContent side="top"><p>复制邀请码</p></TooltipContent>
    </Tooltip>
  );
}

export default function InviteCodesPage() {
  const [codes, setCodes] = useState<InviteCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchInviteCodes();
      setCodes(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const newCode = await generateInviteCode(7);
      setCodes((prev) => [newCode, ...prev]);
      toast.success("邀请码已生成");
    } catch (err) {
      toast.error(`生成失败: ${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleRevoke = async (code: string) => {
    setRevoking(code);
    try {
      await revokeInviteCode(code);
      setCodes((prev) => prev.filter((c) => c.code !== code));
      toast.success("邀请码已吊销");
    } catch (err) {
      toast.error(`吊销失败: ${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setRevoking(null);
    }
  };

  const isRevokable = (code: InviteCode) =>
    !code.used && !(code.expires_at && new Date(code.expires_at) < new Date());

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="h-14 flex items-center justify-between px-4 md:px-6 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">邀请码</h2>
          <span className="text-xs text-muted-foreground font-mono">{codes.length}</span>
        </div>
        <button
          onClick={() => void handleGenerate()}
          disabled={generating}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity duration-fast"
        >
          <Plus className="w-4 h-4" />
          <span className="hidden md:inline">{generating ? "生成中..." : "生成邀请码"}</span>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin mb-3" />
            <p className="text-sm text-muted-foreground">加载中...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
              <AlertTriangle className="w-6 h-6 text-destructive" />
            </div>
            <p className="text-sm font-medium text-foreground mb-1">加载失败</p>
            <p className="text-xs text-muted-foreground mb-4 max-w-xs text-center">{error}</p>
            <button
              onClick={() => void load()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity duration-fast"
            >
              <RefreshCw className="w-3.5 h-3.5" />重试
            </button>
          </div>
        ) : codes.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24">
            <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
              <Ticket className="w-7 h-7 text-primary" />
            </div>
            <p className="text-sm font-semibold text-foreground mb-1">还没有邀请码</p>
            <p className="text-xs text-muted-foreground mb-5 max-w-[220px] text-center leading-relaxed">
              生成邀请码，邀请新成员加入 Mycel
            </p>
            <button
              onClick={() => void handleGenerate()}
              disabled={generating}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity duration-fast"
            >
              <Plus className="w-3.5 h-3.5" />{generating ? "生成中..." : "生成邀请码"}
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-border overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 px-4 py-2.5 bg-muted/50 border-b border-border text-xs text-muted-foreground font-medium">
              <span>邀请码</span>
              <span className="w-20 text-center">状态</span>
              <span className="w-24 text-center hidden sm:block">创建时间</span>
              <span className="w-24 text-center hidden sm:block">过期时间</span>
              <span className="w-16 text-center">操作</span>
            </div>

            {/* Table rows */}
            {codes.map((item) => (
              <div
                key={item.code}
                className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 px-4 py-3 border-b border-border last:border-b-0 items-center hover:bg-muted/30 transition-colors duration-fast"
              >
                {/* Code */}
                <div className="flex items-center gap-2 min-w-0">
                  <code className="text-sm font-mono text-foreground truncate">{item.code}</code>
                </div>

                {/* Status */}
                <div className="w-20 flex justify-center">
                  <StatusBadge code={item} />
                </div>

                {/* Created at */}
                <div className="w-24 text-center hidden sm:block">
                  <span className="text-xs text-muted-foreground">{formatDate(item.created_at)}</span>
                </div>

                {/* Expires at */}
                <div className="w-24 text-center hidden sm:block">
                  <span className="text-xs text-muted-foreground">{formatDate(item.expires_at)}</span>
                </div>

                {/* Actions */}
                <div className="w-16 flex items-center justify-center gap-0.5">
                  <CopyButton text={item.code} />
                  {isRevokable(item) && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => void handleRevoke(item.code)}
                          disabled={revoking === item.code}
                          className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40 transition-colors duration-fast"
                        >
                          {revoking === item.code ? (
                            <div className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top"><p>吊销</p></TooltipContent>
                    </Tooltip>
                  )}
                  {!isRevokable(item) && (
                    <div className="w-7 h-7 flex items-center justify-center text-muted-foreground/20">
                      <TicketX className="w-3.5 h-3.5" />
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
