import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Bot, Search, User, Plus } from "lucide-react";
import ActorAvatar from "@/components/ActorAvatar";
import { useAppStore } from "@/store/app-store";
import { useAuthStore } from "@/store/auth-store";
import CreateAgentDialog from "@/components/CreateAgentDialog";
import { fetchEntities, type EntityItem } from "@/api/entities";

type Tab = "agents" | "contacts";

const statusDot: Record<string, string> = {
  active: "bg-success",
  draft: "bg-warning",
  inactive: "bg-muted-foreground opacity-50",
};

function contactStatusLabel(contact: EntityItem): string {
  if (contact.relationship_state === "visit" || contact.relationship_state === "hire") {
    return contact.relationship_state;
  }
  if (contact.can_chat) return "联系人";
  return contact.relationship_state;
}

export default function ContactList() {
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [entities, setEntities] = useState<EntityItem[]>([]);
  const [contactsLoaded, setContactsLoaded] = useState(false);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [contactsError, setContactsError] = useState<string | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const { id: activeAgentId, userId: activeEntityId } = useParams<{ id?: string; userId?: string }>();
  const tab: Tab = location.pathname.startsWith("/contacts/entities") ? "contacts" : "agents";

  const agentsState = useAppStore((s) => s.agentList);
  const myUserId = useAuthStore((s) => s.userId);

  // Filter user-created agents.
  const agents = agentsState.filter((agent) => !agent.builtin);
  const filtered = search
    ? agents.filter((m) => m.name.toLowerCase().includes(search.toLowerCase()))
    : agents;
  const contacts = useMemo(() => {
    const query = search.trim().toLowerCase();
    return entities
      .filter((entity) => entity.user_id !== myUserId && !entity.is_owned && entity.can_chat)
      .filter((item) => {
        if (!query) return true;
        return [item.name, item.owner_name ?? "", item.type, item.relationship_state].join(" ").toLowerCase().includes(query);
      });
  }, [entities, myUserId, search]);

  const loadContacts = useCallback(async () => {
    if (contactsLoaded || contactsLoading) return;
    setContactsLoading(true);
    setContactsError(null);
    try {
      setEntities(await fetchEntities());
    } catch (err) {
      setContactsError(err instanceof Error ? err.message : String(err));
    } finally {
      setContactsLoaded(true);
      setContactsLoading(false);
    }
  }, [contactsLoaded, contactsLoading]);

  useEffect(() => {
    if (tab === "contacts") void loadContacts();
  }, [loadContacts, tab]);

  return (
    <div className="h-full flex flex-col bg-card border-r border-border">
      {/* Header */}
      <div className="px-4 pt-3 pb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">通讯录</span>
        <button
          aria-label="创建 Agent"
          onClick={() => setCreateOpen(true)}
          className="text-xs text-muted-foreground/50 hover:text-foreground transition-colors duration-fast"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex px-3 gap-1 mb-2">
        <button
          onClick={() => navigate("/contacts")}
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
          onClick={() => {
            navigate("/contacts/entities");
            void loadContacts();
          }}
          className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors duration-fast ${
            tab === "contacts"
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          <User className="w-3.5 h-3.5 inline mr-1" />
          联系人
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
          filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4">
              <p className="text-xs text-muted-foreground">
                {search ? "无匹配结果" : "暂无 Agent"}
              </p>
            </div>
          ) : (
            filtered.map((agent) => {
              const isActive = activeAgentId === agent.id;
              const dot = statusDot[agent.status] || statusDot.inactive;
              return (
                <Link
                  key={agent.id}
                  to={`/contacts/agents/${agent.id}`}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-fast ${
                    isActive ? "bg-background shadow-sm" : "hover:bg-muted"
                  }`}
                >
                  <ActorAvatar
                    name={agent.name}
                    avatarUrl={agent.avatar_url}
                    type="mycel_agent"
                    size="sm"
                  />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm font-medium truncate block">{agent.name}</span>
                    {agent.description && (
                      <span className="text-2xs text-muted-foreground truncate block">
                        {agent.description}
                      </span>
                    )}
                  </div>
                  <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
                </Link>
              );
            })
          )
        ) : (
          contactsLoading ? (
            <div className="flex flex-col items-center justify-center py-12 px-4">
              <p className="text-xs text-muted-foreground">加载联系人...</p>
            </div>
          ) : contactsError ? (
            <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
              <p className="text-xs text-destructive">联系人加载失败</p>
              <p className="mt-1 text-2xs text-muted-foreground break-all">{contactsError}</p>
            </div>
          ) : contacts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4">
              <p className="text-xs text-muted-foreground">{search ? "无匹配结果" : "暂无外部联系人"}</p>
            </div>
          ) : (
            contacts.map((contact) => (
              <Link
                key={contact.user_id}
                to={`/contacts/entities/${contact.user_id}`}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-fast ${
                  activeEntityId === contact.user_id ? "bg-background shadow-sm" : "hover:bg-muted"
                }`}
              >
                <ActorAvatar
                  name={contact.name}
                  avatarUrl={contact.avatar_url ?? undefined}
                  type={contact.type === "agent" ? "mycel_agent" : "human"}
                  size="sm"
                />
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium truncate block">{contact.name}</span>
                  <span className="text-2xs text-muted-foreground truncate block">
                    {contact.owner_name || (contact.type === "agent" ? "Agent" : "联系人")}
                  </span>
                </div>
                <span className="rounded-full bg-muted px-2 py-0.5 text-2xs text-muted-foreground">
                  {contactStatusLabel(contact)}
                </span>
              </Link>
            ))
          )
        )}
      </div>

      <CreateAgentDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
