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
  const agentList = useAppStore(s => s.agentList);
  const loadAll = useAppStore(s => s.loadAll);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (open) {
      loadAll();
      setFilter("");
    }
  }, [open, loadAll]);

  const filtered = useMemo(() => {
    if (!filter) return agentList;
    const q = filter.toLowerCase();
    return agentList.filter(m =>
      m.name.toLowerCase().includes(q) || m.description?.toLowerCase().includes(q)
    );
  }, [agentList, filter]);

  const handleSelect = (member: typeof agentList[0]) => {
    onOpenChange(false);
    navigate(`/chat/hire/${member.id}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md p-0 gap-0">
        <DialogHeader className="px-4 pt-4 pb-3">
          <DialogTitle className="text-base">打开 Agent 默认线程</DialogTitle>
          <DialogDescription className="sr-only">选择 Agent 打开默认线程入口</DialogDescription>
        </DialogHeader>
        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9 h-9 text-sm"
              placeholder="搜索 Agent..."
              value={filter}
              onChange={e => setFilter(e.target.value)}
              autoFocus
            />
          </div>
        </div>
        <div className="border-t max-h-80 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              {agentList.length === 0 ? "暂无 Agent" : "无匹配结果"}
            </p>
          ) : (
            filtered.map(member => (
              <button
                key={member.id}
                onClick={() => handleSelect(member)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted transition-colors duration-fast"
              >
                <MemberAvatar name={member.name} avatarUrl={member.avatar_url} type="mycel_agent" size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{member.name}</span>
                    <span className={`text-2xs px-1.5 py-0.5 rounded-full ${
                      member.status === "active" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
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
