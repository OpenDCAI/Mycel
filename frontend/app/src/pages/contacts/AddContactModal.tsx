import { useEffect, useRef, useState } from "react";
import { Search, UserPlus } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import MemberAvatar from "@/components/MemberAvatar";
import { useRelationshipStore } from "@/store/relationship-store";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

export default function AddContactModal({ open, onOpenChange }: Props) {
  const [query, setQuery] = useState("");
  const { searchResults, searchLoading, searchUsers, clearSearch, relationships, sendRequest } = useRelationshipStore();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [sending, setSending] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!open) { setQuery(""); clearSearch(); }
  }, [open, clearSearch]);

  function handleChange(q: string) {
    setQuery(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void searchUsers(q), 300);
  }

  function getRelState(userId: string) {
    const rel = relationships.find(r => r.other_user_id === userId);
    if (!rel) return null;
    return rel;
  }

  async function handleAdd(userId: string) {
    setSending(s => ({ ...s, [userId]: true }));
    try {
      await sendRequest(userId);
    } finally {
      setSending(s => ({ ...s, [userId]: false }));
    }
  }

  function buttonLabel(userId: string) {
    const rel = getRelState(userId);
    if (!rel) return "添加";
    if (rel.state === "visit" || rel.state === "hire") return "已是好友";
    if (rel.state.startsWith("pending") && rel.is_requester) return "已发送";
    if (rel.state.startsWith("pending") && !rel.is_requester) return "已收到";
    return "添加";
  }

  function buttonDisabled(userId: string) {
    const label = buttonLabel(userId);
    return label !== "添加" || sending[userId];
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>添加联系人</DialogTitle>
        </DialogHeader>
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border mt-2">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            type="text"
            placeholder="搜索 Mycel ID 或姓名..."
            value={query}
            onChange={e => handleChange(e.target.value)}
            className="flex-1 bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground/50"
            autoFocus
          />
        </div>

        <div className="mt-2 space-y-1 max-h-72 overflow-y-auto custom-scrollbar">
          {searchLoading && (
            <div className="py-8 flex justify-center">
              <span className="text-sm text-muted-foreground">搜索中...</span>
            </div>
          )}
          {!searchLoading && query && searchResults.length === 0 && (
            <div className="py-8 flex flex-col items-center gap-2">
              <span className="text-sm text-muted-foreground">无匹配用户</span>
            </div>
          )}
          {!searchLoading && searchResults.map(user => {
            const label = buttonLabel(user.id);
            const disabled = buttonDisabled(user.id);
            return (
              <div key={user.id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-muted transition-colors duration-fast">
                <MemberAvatar name={user.name} avatarUrl={user.avatar_url ?? undefined} type="human" size="sm" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{user.name}</p>
                  {user.mycel_id && (
                    <p className="text-xs text-muted-foreground">#{user.mycel_id}</p>
                  )}
                </div>
                <button
                  onClick={() => void handleAdd(user.id)}
                  disabled={disabled}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-fast ${
                    disabled
                      ? "bg-muted text-muted-foreground cursor-not-allowed"
                      : "bg-primary text-primary-foreground hover:opacity-90"
                  }`}
                >
                  {label === "添加" && <UserPlus className="w-3 h-3" />}
                  {label}
                </button>
              </div>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
