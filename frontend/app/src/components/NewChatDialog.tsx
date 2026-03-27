import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Search, MessageSquare } from "lucide-react";
import MemberAvatar from "./MemberAvatar";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { Input } from "./ui/input";
import { useAppStore } from "@/store/app-store";

interface NewChatDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function NewChatDialog({ open, onOpenChange }: NewChatDialogProps) {
  const navigate = useNavigate();
  const memberList = useAppStore(s => s.memberList);
  const loadAll = useAppStore(s => s.loadAll);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (open) {
      loadAll();
      setFilter("");
    }
  }, [open, loadAll]);

  const filtered = useMemo(() => {
    if (!filter) return memberList;
    const q = filter.toLowerCase();
    return memberList.filter(m =>
      m.name.toLowerCase().includes(q) || m.description?.toLowerCase().includes(q)
    );
  }, [memberList, filter]);

  const handleSelect = (member: typeof memberList[0]) => {
    onOpenChange(false);
    navigate(`/threads/${member.id}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md p-0 gap-0">
        <DialogHeader className="px-4 pt-4 pb-3">
          <DialogTitle className="text-base">发起会话</DialogTitle>
          <DialogDescription className="sr-only">选择成员发起新对话</DialogDescription>
        </DialogHeader>
        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9 h-9 text-sm"
              placeholder="搜索成员..."
              value={filter}
              onChange={e => setFilter(e.target.value)}
              autoFocus
            />
          </div>
        </div>
        <div className="border-t max-h-80 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              {memberList.length === 0 ? "暂无成员" : "无匹配结果"}
            </p>
          ) : (
            filtered.map(member => (
              <button
                key={member.id}
                onClick={() => handleSelect(member)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted transition-colors"
              >
                <MemberAvatar name={member.name} avatarUrl={member.avatar_url} type="mycel_agent" size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{member.name}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      member.status === "active" ? "bg-green-100 text-green-700" : "bg-muted text-muted-foreground"
                    }`}>
                      {member.status === "active" ? "在线" : member.status === "draft" ? "草稿" : "离线"}
                    </span>
                  </div>
                  {member.description && (
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{member.description}</p>
                  )}
                </div>
                <MessageSquare className="h-4 w-4 text-muted-foreground shrink-0" />
              </button>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
