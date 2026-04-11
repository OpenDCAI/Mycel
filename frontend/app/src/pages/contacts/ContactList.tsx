import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bot, Search, User, Plus } from "lucide-react";
import ActorAvatar from "@/components/ActorAvatar";
import { useAppStore } from "@/store/app-store";
import CreateAgentDialog from "@/components/CreateAgentDialog";

type Tab = "agents" | "contacts";

const statusDot: Record<string, string> = {
  active: "bg-success",
  draft: "bg-warning",
  inactive: "bg-muted-foreground opacity-50",
};

export default function ContactList() {
  const [tab, setTab] = useState<Tab>("agents");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const { id: activeId } = useParams<{ id?: string }>();

  const agentsState = useAppStore((s) => s.agentList);
  const fetchAgents = useAppStore((s) => s.fetchAgents);

  useEffect(() => {
    void fetchAgents();
  }, [fetchAgents]);

  // Filter agents (non-builtin members)
  const agents = agentsState.filter((m) => !m.builtin);
  const filtered = search
    ? agents.filter((m) => m.name.toLowerCase().includes(search.toLowerCase()))
    : agents;

  return (
    <div className="h-full flex flex-col bg-card border-r border-border">
      {/* Header */}
      <div className="px-4 pt-3 pb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">通讯录</span>
        <button
          onClick={() => setCreateOpen(true)}
          className="text-xs text-muted-foreground/50 hover:text-foreground transition-colors duration-fast"
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
          <div className="flex flex-col items-center justify-center py-12 px-4">
            <p className="text-xs text-muted-foreground">联系人功能即将上线</p>
          </div>
        )}
      </div>

      <CreateAgentDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
