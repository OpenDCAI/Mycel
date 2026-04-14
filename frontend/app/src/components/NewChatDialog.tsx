import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, MessageSquare, Search, Users } from "lucide-react";
import ActorAvatar from "./ActorAvatar";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { Input } from "./ui/input";
import { useAppStore } from "@/store/app-store";
import { authFetch, useAuthStore } from "@/store/auth-store";
import { fetchUserChatCandidates, type UserChatCandidate } from "@/api/users";

interface NewChatDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type DialogMode = "thread" | "group";

async function createChat(userIds: string[], title: string | null): Promise<string> {
  const body: Record<string, unknown> = { user_ids: userIds };
  if (title) body.title = title;
  const response = await authFetch("/api/chats", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  const payload = await response.json();
  if (!payload || typeof payload !== "object" || typeof (payload as Record<string, unknown>).id !== "string") {
    throw new Error("Malformed chat create response");
  }
  return (payload as { id: string }).id;
}

export default function NewChatDialog({ open, onOpenChange }: NewChatDialogProps) {
  const navigate = useNavigate();
  const agentList = useAppStore(s => s.agentList);
  const myUserId = useAuthStore(s => s.userId);
  const [filter, setFilter] = useState("");
  const [mode, setMode] = useState<DialogMode>("thread");
  const [chatCandidates, setChatCandidates] = useState<UserChatCandidate[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [groupTitle, setGroupTitle] = useState("");
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [candidatesLoaded, setCandidatesLoaded] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!filter) return agentList;
    const q = filter.toLowerCase();
    return agentList.filter(agent =>
      agent.name.toLowerCase().includes(q) || agent.description?.toLowerCase().includes(q)
    );
  }, [agentList, filter]);

  const groupCandidates = useMemo(() => {
    const query = filter.trim().toLowerCase();
    const items = chatCandidates.filter((item) => item.user_id !== myUserId && (item.is_owned || item.can_chat));
    if (!query) return items;
    return items.filter((item) => [item.name, item.owner_name ?? "", item.type].join(" ").toLowerCase().includes(query));
  }, [chatCandidates, filter, myUserId]);

  useEffect(() => {
    if (!open) return;
    setFilter("");
    setSelectedIds([]);
    setGroupTitle("");
    setChatCandidates([]);
    setCandidatesLoaded(false);
    setError(null);
  }, [open]);

  useEffect(() => {
    if (!open || mode !== "group" || candidatesLoaded || loadingCandidates) return;
    setLoadingCandidates(true);
    setError(null);
    fetchUserChatCandidates()
      .then(setChatCandidates)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => {
        setCandidatesLoaded(true);
        setLoadingCandidates(false);
      });
  }, [candidatesLoaded, loadingCandidates, mode, open]);

  const handleSelect = (agent: typeof agentList[0]) => {
    onOpenChange(false);
    navigate(`/chat/hire/new/${agent.id}`);
  };

  const toggleSelected = (userId: string) => {
    setSelectedIds((current) =>
      current.includes(userId) ? current.filter((id) => id !== userId) : [...current, userId],
    );
  };

  const handleCreateGroup = async () => {
    if (!myUserId) {
      setError("无法创建群聊：当前用户未登录");
      return;
    }
    if (selectedIds.length < 2 || creating) return;
    setCreating(true);
    setError(null);
    try {
      const chatId = await createChat([myUserId, ...selectedIds], groupTitle.trim() || null);
      onOpenChange(false);
      navigate(`/chat/visit/${chatId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md p-0 gap-0">
        <DialogHeader className="px-4 pt-4 pb-3">
          <DialogTitle className="text-base">{mode === "thread" ? "创建 Agent 新线程" : "创建群聊"}</DialogTitle>
          <DialogDescription className="sr-only">
            {mode === "thread" ? "选择 Agent 进入新线程创建入口" : "选择联系人创建群聊"}
          </DialogDescription>
        </DialogHeader>
        <div className="px-4 pb-3">
          <div className="grid grid-cols-2 rounded-lg border border-border bg-muted/40 p-0.5">
            <button
              type="button"
              onClick={() => setMode("thread")}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-fast ${
                mode === "thread" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              新线程
            </button>
            <button
              type="button"
              onClick={() => setMode("group")}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-fast ${
                mode === "group" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              创建群聊
            </button>
          </div>
        </div>
        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9 h-9 text-sm"
              placeholder={mode === "thread" ? "搜索 Agent..." : "搜索联系人或 Agent..."}
              value={filter}
              onChange={e => setFilter(e.target.value)}
              autoFocus
            />
          </div>
        </div>
        {mode === "group" && selectedIds.length >= 2 && (
          <div className="px-4 pb-3">
            <Input
              className="h-9 text-sm"
              placeholder="群聊名称（可选）"
              value={groupTitle}
              onChange={(e) => setGroupTitle(e.target.value)}
            />
          </div>
        )}
        {error && (
          <div className="mx-4 mb-3 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}
        <div className="border-t max-h-80 overflow-y-auto">
          {mode === "thread" && filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              {agentList.length === 0 ? "暂无 Agent" : "无匹配结果"}
            </p>
          ) : mode === "thread" ? (
            filtered.map(agent => (
              <button
                key={agent.id}
                onClick={() => handleSelect(agent)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted transition-colors duration-fast"
              >
                <ActorAvatar name={agent.name} avatarUrl={agent.avatar_url} type="mycel_agent" size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{agent.name}</span>
                    <span className={`text-2xs px-1.5 py-0.5 rounded-full ${
                      agent.status === "active" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
                    }`}>
                      {agent.status === "active" ? "在线" : agent.status === "draft" ? "草稿" : "离线"}
                    </span>
                  </div>
                  {agent.description && (
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{agent.description}</p>
                  )}
                </div>
                <MessageSquare className="h-4 w-4 text-muted-foreground shrink-0" />
              </button>
            ))
          ) : loadingCandidates ? (
            <p className="text-sm text-muted-foreground text-center py-8">加载联系人...</p>
          ) : groupCandidates.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">暂无可选联系人</p>
          ) : (
            groupCandidates.map(candidate => {
              const selected = selectedIds.includes(candidate.user_id);
              return (
                <button
                  key={candidate.user_id}
                  onClick={() => toggleSelected(candidate.user_id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors duration-fast ${
                    selected ? "bg-primary/5" : "hover:bg-muted"
                  }`}
                >
                  <ActorAvatar
                    name={candidate.name}
                    avatarUrl={candidate.avatar_url ?? undefined}
                    type={candidate.type === "agent" ? "mycel_agent" : "human"}
                    size="sm"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{candidate.name}</span>
                      <span className="text-2xs px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
                        {candidate.type === "agent" ? "Agent" : "联系人"}
                      </span>
                    </div>
                    {candidate.owner_name && (
                      <p className="text-xs text-muted-foreground truncate mt-0.5">{candidate.owner_name}</p>
                    )}
                  </div>
                  {selected ? <Check className="h-4 w-4 text-primary shrink-0" /> : <Users className="h-4 w-4 text-muted-foreground shrink-0" />}
                </button>
              );
            })
          )}
        </div>
        {mode === "group" && (
          <div className="border-t px-4 py-3">
            <button
              type="button"
              onClick={() => void handleCreateGroup()}
              disabled={selectedIds.length < 2 || creating}
              className="w-full rounded-lg bg-foreground px-3 py-2 text-sm font-medium text-background transition-colors duration-fast hover:bg-foreground/90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {creating ? "创建中..." : `创建群聊（${selectedIds.length}）`}
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
