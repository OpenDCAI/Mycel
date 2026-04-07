import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bot, Check, MoreHorizontal, Plus, Search, User, X } from "lucide-react";
import MemberAvatar from "@/components/MemberAvatar";
import { useAppStore } from "@/store/app-store";
import CreateMemberDialog from "@/components/CreateMemberDialog";
import { useRelationshipStore } from "@/store/relationship-store";
import { useAuthStore } from "@/store/auth-store";
import { authFetch } from "@/store/auth-store";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import AddContactModal from "./AddContactModal";

type Tab = "agents" | "contacts";

const statusDot: Record<string, string> = {
  active: "bg-success",
  draft: "bg-warning",
  inactive: "bg-muted-foreground opacity-50",
};

function groupByFirstLetter(items: { other_name: string; [key: string]: unknown }[]) {
  const groups: Record<string, typeof items> = {};
  for (const item of items) {
    const first = item.other_name?.[0]?.toUpperCase() ?? "#";
    const key = /[A-Z]/.test(first) ? first : "#";
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return Object.entries(groups).sort(([a], [b]) => {
    if (a === "#") return 1;
    if (b === "#") return -1;
    return a.localeCompare(b);
  });
}

export default function ContactList() {
  const [tab, setTab] = useState<Tab>("agents");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [addContactOpen, setAddContactOpen] = useState(false);
  const { id: activeId } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const members = useAppStore((s) => s.memberList);
  const fetchMembers = useAppStore((s) => s.fetchMembers);
  const myUserId = useAuthStore(s => s.userId);

  const { relationships, loading: relLoading, fetchRelationships, approve, reject, remove } = useRelationshipStore();

  useEffect(() => { void fetchMembers(); }, [fetchMembers]);
  useEffect(() => {
    if (tab === "contacts") void fetchRelationships();
  }, [tab, fetchRelationships]);

  // Agents
  const agents = members.filter((m) => !m.builtin);
  const filteredAgents = search
    ? agents.filter((m) => m.name.toLowerCase().includes(search.toLowerCase()))
    : agents;

  // Relationships
  const pendingIncoming = relationships.filter(r => r.state.startsWith("pending") && !r.is_requester);
  const pendingOutgoing = relationships.filter(r => r.state.startsWith("pending") && r.is_requester);
  const activeContacts = relationships.filter(r => r.state === "visit" || r.state === "hire");

  const filteredContacts = search
    ? activeContacts.filter(r => r.other_name.toLowerCase().includes(search.toLowerCase()))
    : activeContacts;

  const grouped = groupByFirstLetter(filteredContacts);

  const pendingCount = pendingIncoming.length;

  const handleSendMessage = useCallback(async (otherUserId: string) => {
    if (!myUserId) return;
    try {
      const res = await authFetch("/api/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_ids: [myUserId, otherUserId] }),
      });
      if (res.ok) {
        const data = await res.json();
        navigate(`/chat/visit/${data.id}`);
      }
    } catch (err) {
      console.error("Failed to open chat:", err);
    }
  }, [myUserId, navigate]);

  return (
    <div className="h-full flex flex-col bg-card border-r border-border">
      {/* Header */}
      <div className="px-4 pt-3 pb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">通讯录</span>
        <button
          onClick={() => tab === "contacts" ? setAddContactOpen(true) : setCreateOpen(true)}
          className="text-muted-foreground/50 hover:text-foreground transition-colors duration-fast"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex px-3 gap-1 mb-2">
        <button
          onClick={() => setTab("agents")}
          className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors duration-fast ${
            tab === "agents"
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          <Bot className="w-3.5 h-3.5 inline mr-1" />
          Agent
        </button>
        <button
          onClick={() => setTab("contacts")}
          className={`relative flex-1 py-1.5 text-xs font-medium rounded-md transition-colors duration-fast ${
            tab === "contacts"
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          <User className="w-3.5 h-3.5 inline mr-1" />
          联系人
          {pendingCount > 0 && (
            <span className="absolute -top-1 -right-1 min-w-4 h-4 rounded-full bg-destructive text-destructive-foreground text-2xs flex items-center justify-center px-1">
              {pendingCount}
            </span>
          )}
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/50 border border-border">
          <Search className="w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜索..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground/50"
          />
        </div>
      </div>

      <div className="h-px mx-3 bg-border" />

      {/* List */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2 pt-2 space-y-0.5 custom-scrollbar">
        {tab === "agents" ? (
          filteredAgents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4">
              <p className="text-xs text-muted-foreground">
                {search ? "无匹配结果" : "暂无 Agent"}
              </p>
            </div>
          ) : (
            filteredAgents.map((agent) => {
              const isActive = activeId === agent.id;
              const dot = statusDot[agent.status] || statusDot.inactive;
              return (
                <Link
                  key={agent.id}
                  to={`/contacts/agents/${agent.id}`}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-fast ${
                    isActive ? "bg-background shadow-sm" : "hover:bg-muted"
                  }`}
                >
                  <MemberAvatar name={agent.name} avatarUrl={agent.avatar_url} type="mycel_agent" size="sm" />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm font-medium truncate block">{agent.name}</span>
                    {agent.description && (
                      <span className="text-2xs text-muted-foreground truncate block">{agent.description}</span>
                    )}
                  </div>
                  <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
                </Link>
              );
            })
          )
        ) : relLoading ? (
          <div className="space-y-0.5">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="px-3 py-2 rounded-lg animate-pulse">
                <div className="h-4 w-[60%] bg-muted rounded mb-1" />
                <div className="h-3 w-[40%] bg-muted rounded" />
              </div>
            ))}
          </div>
        ) : (
          <>
            {/* Pending requests section */}
            {(pendingIncoming.length > 0 || pendingOutgoing.length > 0) && (
              <div className="mb-2">
                <div className="px-3 py-1.5 flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">好友申请</span>
                  {pendingCount > 0 && (
                    <span className="min-w-4 h-4 rounded-full bg-destructive text-destructive-foreground text-2xs flex items-center justify-center px-1">
                      {pendingCount}
                    </span>
                  )}
                </div>
                {pendingIncoming.map(r => (
                  <div key={r.id} className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-muted transition-colors duration-fast">
                    <MemberAvatar name={r.other_name} avatarUrl={r.other_avatar_url ?? undefined} type="human" size="sm" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{r.other_name}</p>
                      {r.other_mycel_id && <p className="text-xs text-muted-foreground">#{r.other_mycel_id}</p>}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => void approve(r.id)}
                        className="p-1.5 rounded-lg bg-success/10 text-success hover:bg-success/20 transition-colors duration-fast"
                        title="同意"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => void reject(r.id)}
                        className="p-1.5 rounded-lg bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors duration-fast"
                        title="拒绝"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
                {pendingOutgoing.map(r => (
                  <div key={r.id} className="flex items-center gap-2.5 px-3 py-2 rounded-lg">
                    <MemberAvatar name={r.other_name} avatarUrl={r.other_avatar_url ?? undefined} type="human" size="sm" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{r.other_name}</p>
                      {r.other_mycel_id && <p className="text-xs text-muted-foreground">#{r.other_mycel_id}</p>}
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0">等待对方同意...</span>
                  </div>
                ))}
                <div className="h-px mx-1 bg-border my-2" />
              </div>
            )}

            {/* Active contacts grouped */}
            {filteredContacts.length === 0 && pendingIncoming.length === 0 && pendingOutgoing.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 px-4">
                <p className="text-xs text-muted-foreground">
                  {search ? "无匹配结果" : "暂无联系人，点击 + 添加好友"}
                </p>
              </div>
            ) : (
              grouped.map(([letter, contacts]) => (
                <div key={letter}>
                  <div className="px-3 py-1">
                    <span className="text-xs font-semibold text-muted-foreground">{letter}</span>
                  </div>
                  {contacts.map(contact => {
                    const r = contact as typeof filteredContacts[0];
                    return (
                      <div key={r.id} className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-muted transition-colors duration-fast group">
                        <MemberAvatar name={r.other_name} avatarUrl={r.other_avatar_url ?? undefined} type="human" size="sm" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{r.other_name}</p>
                          {r.other_mycel_id && <p className="text-xs text-muted-foreground">#{r.other_mycel_id}</p>}
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button className="p-1 rounded text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-all duration-fast">
                              <MoreHorizontal className="w-4 h-4" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => void handleSendMessage(r.other_user_id)}>
                              发消息
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => void remove(r.id)}
                            >
                              删除好友
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </>
        )}
      </div>

      <CreateMemberDialog open={createOpen} onOpenChange={setCreateOpen} />
      <AddContactModal open={addContactOpen} onOpenChange={setAddContactOpen} />
    </div>
  );
}
