// @ts-nocheck — legacy page, not in active routing
import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search, Bot, User, Users, Plus, MessageSquare,
  Zap, Wrench, Plug, UserPlus, X, Check, Clock,
} from "lucide-react";
import MemberAvatar from "@/components/MemberAvatar";
import { useAppStore } from "@/store/app-store";
import { authFetch, useAuthStore } from "@/store/auth-store";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ChatEntry as ChatEntity } from "@/api/types";
import type { Member } from "@/store/types";

// ── Types ────────────────────────────────────────────────────────────────

type TabId = "agents" | "contacts" | "groups";

interface RelationshipRow {
  id: string;
  requester_id: string;
  addressee_id: string;
  status: "pending" | "accepted" | "blocked";
  created_at: string;
  peer_id: string;
  peer_name: string;
  peer_avatar_url?: string;
  peer_type: string;
  direction: "outgoing" | "incoming";
}

interface GroupInfo {
  id: string;
  title: string | null;
  entities: ChatEntity[];
  member_count: number;
}

// ── Tab definitions ──────────────────────────────────────────────────────

const tabs: { id: TabId; label: string; icon: typeof Bot }[] = [
  { id: "agents", label: "Agent", icon: Bot },
  { id: "contacts", label: "联系人", icon: User },
  { id: "groups", label: "群聊", icon: Users },
];

// ── Main Component ───────────────────────────────────────────────────────

export default function ContactsPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>("agents");
  const [search, setSearch] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);

  // Agent data from existing store
  const memberList = useAppStore(s => s.memberList);
  const loadAll = useAppStore(s => s.loadAll);
  useEffect(() => { loadAll(); }, [loadAll]);

  // Contacts (relationships)
  const [relationships, setRelationships] = useState<RelationshipRow[]>([]);
  const [relLoading, setRelLoading] = useState(true);

  const refreshRelationships = useCallback(() => {
    authFetch("/api/relationships")
      .then(r => r.json())
      .then((data: RelationshipRow[]) => setRelationships(data))
      .catch(console.error)
      .finally(() => setRelLoading(false));
  }, []);

  useEffect(() => { refreshRelationships(); }, [refreshRelationships]);

  // Groups (multi-party chats)
  const myEntityId = useAuthStore(s => s.userId);
  const [groups, setGroups] = useState<GroupInfo[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(true);

  const refreshGroups = useCallback(() => {
    authFetch("/api/chats")
      .then(r => r.json())
      .then((data: { id: string; title: string | null; entities: ChatEntity[]; }[]) => {
        const groupChats = data.filter(c => c.entities.length > 2);
        setGroups(groupChats.map(c => ({
          id: c.id,
          title: c.title,
          entities: c.entities,
          member_count: c.entities.length,
        })));
      })
      .catch(console.error)
      .finally(() => setGroupsLoading(false));
  }, []);

  useEffect(() => { refreshGroups(); }, [refreshGroups]);

  // Filtered lists
  const filteredAgents = useMemo(() => {
    if (!search) return memberList;
    const q = search.toLowerCase();
    return memberList.filter(m =>
      m.name.toLowerCase().includes(q) || m.description.toLowerCase().includes(q)
    );
  }, [memberList, search]);

  const acceptedContacts = useMemo(() =>
    relationships.filter(r => r.status === "accepted"),
    [relationships]
  );

  const pendingContacts = useMemo(() =>
    relationships.filter(r => r.status === "pending"),
    [relationships]
  );

  const filteredContacts = useMemo(() => {
    if (!search) return acceptedContacts;
    const q = search.toLowerCase();
    return acceptedContacts.filter(r => r.peer_name.toLowerCase().includes(q));
  }, [acceptedContacts, search]);

  const filteredGroups = useMemo(() => {
    if (!search) return groups;
    const q = search.toLowerCase();
    return groups.filter(g => {
      const name = g.title || g.entities.map(e => e.name).join(", ");
      return name.toLowerCase().includes(q);
    });
  }, [groups, search]);

  // Selected detail data
  const selectedAgent = useMemo(() =>
    memberList.find(m => m.id === selectedAgentId) || null,
    [memberList, selectedAgentId]
  );

  const selectedContact = useMemo(() =>
    relationships.find(r => r.peer_id === selectedContactId) || null,
    [relationships, selectedContactId]
  );

  const selectedGroup = useMemo(() =>
    groups.find(g => g.id === selectedGroupId) || null,
    [groups, selectedGroupId]
  );

  // Auto-select first item when tab changes
  useEffect(() => {
    if (activeTab === "agents" && !selectedAgentId && filteredAgents.length > 0) {
      setSelectedAgentId(filteredAgents[0].id);
    }
  }, [activeTab, filteredAgents, selectedAgentId]);

  useEffect(() => {
    if (activeTab === "contacts" && !selectedContactId && filteredContacts.length > 0) {
      setSelectedContactId(filteredContacts[0].peer_id);
    }
  }, [activeTab, filteredContacts, selectedContactId]);

  useEffect(() => {
    if (activeTab === "groups" && !selectedGroupId && filteredGroups.length > 0) {
      setSelectedGroupId(filteredGroups[0].id);
    }
  }, [activeTab, filteredGroups, selectedGroupId]);

  const handleStartChat = (entityId: string) => {
    navigate("/chats", { state: { startWith: entityId } });
  };

  const handleAcceptRelationship = async (relationshipId: string) => {
    try {
      await authFetch(`/api/relationships/${relationshipId}/accept`, { method: "POST" });
      refreshRelationships();
    } catch (e) {
      console.error("Accept failed:", e);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left panel — list */}
      <div className="w-72 h-full flex flex-col bg-card border-r border-border shrink-0">
        {/* Header */}
        <div className="px-4 pt-3 pb-1 flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">通讯录</span>
          <span className="text-xs text-muted-foreground font-mono">
            {activeTab === "agents" ? filteredAgents.length
              : activeTab === "contacts" ? filteredContacts.length
              : filteredGroups.length}
          </span>
        </div>

        {/* Search */}
        <div className="px-3 pb-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索..."
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-muted/50 border border-transparent text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:border-primary/30 transition-colors duration-fast"
            />
          </div>
        </div>

        {/* Tabs */}
        <div className="px-3 pb-2 flex gap-1">
          {tabs.map(tab => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors duration-fast ${
                  isActive
                    ? "bg-foreground text-background"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <tab.icon className="w-3 h-3" />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="h-px mx-3 bg-border" />

        {/* List */}
        <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2 space-y-0.5 custom-scrollbar">
          {activeTab === "agents" && (
            <>
              {filteredAgents.length === 0 ? (
                <EmptyListHint text="暂无 Agent" actionText="前往市场添加" onAction={() => navigate("/marketplace")} />
              ) : filteredAgents.map(m => (
                <ContactListItem
                  key={m.id}
                  name={m.name}
                  avatarUrl={m.avatar_url}
                  type="mycel_agent"
                  subtitle={m.description}
                  isActive={selectedAgentId === m.id}
                  onClick={() => setSelectedAgentId(m.id)}
                  statusDot={m.status === "active" ? "bg-success" : m.status === "draft" ? "bg-warning" : undefined}
                />
              ))}
            </>
          )}

          {activeTab === "contacts" && (
            <>
              {/* Pending requests */}
              {pendingContacts.length > 0 && (
                <div className="mb-2">
                  <p className="px-2 py-1 text-2xs font-medium text-muted-foreground/60 uppercase tracking-wider">
                    待处理 ({pendingContacts.length})
                  </p>
                  {pendingContacts.map(r => (
                    <div key={r.id} className="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-muted transition-colors duration-fast">
                      <MemberAvatar name={r.peer_name} avatarUrl={r.peer_avatar_url} type={r.peer_type} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{r.peer_name}</p>
                        <p className="text-2xs text-muted-foreground">
                          {r.direction === "incoming" ? "请求添加你" : "等待对方确认"}
                        </p>
                      </div>
                      {r.direction === "incoming" && (
                        <button
                          onClick={() => handleAcceptRelationship(r.id)}
                          className="w-6 h-6 rounded-md bg-primary/10 text-primary flex items-center justify-center hover:bg-primary/20 transition-colors duration-fast"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {r.direction === "outgoing" && (
                        <Clock className="w-3.5 h-3.5 text-muted-foreground/40" />
                      )}
                    </div>
                  ))}
                  <div className="h-px mx-2 my-1 bg-border" />
                </div>
              )}

              {filteredContacts.length === 0 && pendingContacts.length === 0 ? (
                <EmptyListHint text="暂无联系人" />
              ) : filteredContacts.map(r => (
                <ContactListItem
                  key={r.peer_id}
                  name={r.peer_name}
                  avatarUrl={r.peer_avatar_url}
                  type={r.peer_type}
                  isActive={selectedContactId === r.peer_id}
                  onClick={() => setSelectedContactId(r.peer_id)}
                />
              ))}
            </>
          )}

          {activeTab === "groups" && (
            <>
              {filteredGroups.length === 0 ? (
                <EmptyListHint text="暂无群聊" actionText="创建群聊" onAction={() => navigate("/chats")} />
              ) : filteredGroups.map(g => {
                const name = g.title || g.entities.map(e => e.name).join(", ");
                return (
                  <ContactListItem
                    key={g.id}
                    name={name}
                    type="group"
                    subtitle={`${g.member_count} 位成员`}
                    isActive={selectedGroupId === g.id}
                    onClick={() => setSelectedGroupId(g.id)}
                    groupEntities={g.entities}
                  />
                );
              })}
            </>
          )}
        </div>
      </div>

      {/* Right panel — detail */}
      <div className="flex-1 min-w-0 bg-background overflow-y-auto">
        {activeTab === "agents" && (
          selectedAgent ? (
            <AgentDetail
              member={selectedAgent}
              onStartChat={() => handleStartChat(selectedAgent.id)}
              onViewDetail={() => navigate(`/members/${selectedAgent.id}`)}
            />
          ) : (
            <DetailEmpty text="选择一个 Agent 查看详情" />
          )
        )}

        {activeTab === "contacts" && (
          selectedContact ? (
            <ContactDetail
              contact={selectedContact}
              onStartChat={() => handleStartChat(selectedContact.peer_id)}
            />
          ) : (
            <DetailEmpty text="选择联系人查看详情" />
          )
        )}

        {activeTab === "groups" && (
          selectedGroup ? (
            <GroupDetail
              group={selectedGroup}
              myEntityId={myEntityId}
              onEnterChat={() => navigate(`/chats/${selectedGroup.id}`)}
            />
          ) : (
            <DetailEmpty text="选择群聊查看详情" />
          )
        )}
      </div>
    </div>
  );
}

// ── List Item ────────────────────────────────────────────────────────────

function ContactListItem({
  name, avatarUrl, type, subtitle, isActive, onClick, statusDot, groupEntities,
}: {
  name: string;
  avatarUrl?: string;
  type: string;
  subtitle?: string;
  isActive: boolean;
  onClick: () => void;
  statusDot?: string;
  groupEntities?: ChatEntity[];
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors duration-fast ${
        isActive ? "bg-muted" : "hover:bg-muted/60"
      }`}
    >
      {groupEntities ? (
        <GroupAvatar entities={groupEntities} />
      ) : (
        <div className="relative">
          <MemberAvatar name={name} avatarUrl={avatarUrl} type={type} size="sm" />
          {statusDot && (
            <span className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full ${statusDot} ring-2 ring-card`} />
          )}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className={`text-sm truncate ${isActive ? "font-semibold text-foreground" : "font-medium text-foreground"}`}>
          {name}
        </p>
        {subtitle && (
          <p className="text-2xs text-muted-foreground/60 truncate">{subtitle}</p>
        )}
      </div>
    </button>
  );
}

// ── Group Avatar (2x2 grid) ──────────────────────────────────────────────

function GroupAvatar({ entities }: { entities: ChatEntity[] }) {
  const shown = entities.slice(0, 4);
  return (
    <div className="w-7 h-7 rounded-lg bg-muted grid grid-cols-2 gap-px overflow-hidden shrink-0">
      {shown.map((e, i) => (
        <div key={e.id || i} className="bg-card flex items-center justify-center">
          <span className="text-3xs font-medium text-muted-foreground">
            {e.name.charAt(0).toUpperCase()}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Agent Detail ─────────────────────────────────────────────────────────

function AgentDetail({ member, onStartChat, onViewDetail }: {
  member: Member;
  onStartChat: () => void;
  onViewDetail: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"role" | "skills" | "mcp">("role");

  const statusLabels: Record<string, { label: string; color: string }> = {
    active: { label: "在线", color: "bg-success" },
    draft: { label: "草稿", color: "bg-warning" },
    inactive: { label: "离线", color: "bg-muted-foreground" },
  };
  const status = statusLabels[member.status] || statusLabels.inactive;

  return (
    <div className="h-full flex">
      {/* Left: Profile card */}
      <div className="w-64 shrink-0 border-r border-border p-6 flex flex-col items-center">
        <MemberAvatar
          name={member.name}
          avatarUrl={member.avatar_url}
          type="mycel_agent"
          size="lg"
          className="rounded-2xl mb-4"
        />

        <h2 className="text-sm font-semibold text-foreground text-center mb-1">{member.name}</h2>
        <p className="text-xs text-muted-foreground text-center mb-3 line-clamp-3">{member.description}</p>

        {/* Status + version */}
        <div className="flex items-center gap-2 mb-4">
          <span className={`w-1.5 h-1.5 rounded-full ${status.color}`} />
          <span className="text-xs text-muted-foreground">{status.label}</span>
          <span className="text-2xs text-muted-foreground/40">v{member.version}</span>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-4 mb-6">
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex flex-col items-center gap-0.5 cursor-default">
                <span className="text-sm font-semibold text-foreground">{member.config.skills.length}</span>
                <span className="text-2xs text-muted-foreground">技能</span>
              </div>
            </TooltipTrigger>
            <TooltipContent>Skills</TooltipContent>
          </Tooltip>
          <div className="w-px h-6 bg-border" />
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex flex-col items-center gap-0.5 cursor-default">
                <span className="text-sm font-semibold text-foreground">{member.config.tools.filter(t => t.enabled).length}</span>
                <span className="text-2xs text-muted-foreground">工具</span>
              </div>
            </TooltipTrigger>
            <TooltipContent>Active tools</TooltipContent>
          </Tooltip>
          <div className="w-px h-6 bg-border" />
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex flex-col items-center gap-0.5 cursor-default">
                <span className="text-sm font-semibold text-foreground">{member.config.mcps.length}</span>
                <span className="text-2xs text-muted-foreground">MCP</span>
              </div>
            </TooltipTrigger>
            <TooltipContent>MCP servers</TooltipContent>
          </Tooltip>
        </div>

        {/* CTA buttons */}
        <button
          onClick={onStartChat}
          className="w-full py-2 rounded-lg bg-foreground text-background text-sm font-medium hover:bg-foreground/90 transition-colors duration-fast mb-2"
        >
          <MessageSquare className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
          发起对话
        </button>
        <button
          onClick={onViewDetail}
          className="w-full py-2 rounded-lg bg-muted text-foreground text-sm font-medium hover:bg-muted/80 transition-colors duration-fast"
        >
          编辑配置
        </button>
      </div>

      {/* Right: Tabs content */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Tab bar */}
        <div className="flex items-center gap-1 px-4 pt-4 pb-2">
          {([
            { id: "role" as const, label: "行为准则", icon: Bot },
            { id: "skills" as const, label: "技能 & 工具", icon: Zap },
            { id: "mcp" as const, label: "MCP", icon: Plug },
          ]).map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-fast ${
                activeTab === t.id
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <t.icon className="w-3 h-3" />
              {t.label}
            </button>
          ))}
        </div>

        <div className="h-px mx-4 bg-border" />

        {/* Tab content */}
        <div className="flex-1 min-h-0 overflow-y-auto p-4">
          {activeTab === "role" && (
            <div className="space-y-3">
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">System Prompt</h3>
              {member.config.prompt ? (
                <pre className="text-sm text-foreground/80 whitespace-pre-wrap font-mono bg-muted/30 rounded-lg p-3 max-h-96 overflow-y-auto">
                  {member.config.prompt}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground/60">未设置</p>
              )}

              {member.config.rules.length > 0 && (
                <>
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mt-4">
                    规则 ({member.config.rules.length})
                  </h3>
                  <div className="space-y-2">
                    {member.config.rules.map(r => (
                      <div key={r.name} className="rounded-lg border border-border p-3">
                        <p className="text-xs font-medium text-foreground mb-1">{r.name}</p>
                        <p className="text-xs text-muted-foreground line-clamp-3 font-mono">{r.content || "( 空 )"}</p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === "skills" && (
            <div className="space-y-4">
              {/* Skills */}
              <div>
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  技能 ({member.config.skills.length})
                </h3>
                {member.config.skills.length === 0 ? (
                  <p className="text-sm text-muted-foreground/60">未配置技能</p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {member.config.skills.map(s => (
                      <div key={s.name} className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${
                        s.enabled ? "border-border" : "border-border opacity-50"
                      }`}>
                        <Zap className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-medium truncate">{s.name}</p>
                          {s.desc && <p className="text-2xs text-muted-foreground truncate">{s.desc}</p>}
                        </div>
                        <span className={`w-1.5 h-1.5 rounded-full ${s.enabled ? "bg-success" : "bg-muted-foreground/30"}`} />
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Tools */}
              <div>
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  工具 ({member.config.tools.filter(t => t.enabled).length}/{member.config.tools.length})
                </h3>
                {member.config.tools.length === 0 ? (
                  <p className="text-sm text-muted-foreground/60">未配置工具</p>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1.5">
                    {member.config.tools.map(t => (
                      <div key={t.name} className={`flex items-center gap-1.5 rounded border px-2 py-1.5 text-xs ${
                        t.enabled ? "" : "opacity-40"
                      }`}>
                        <Wrench className="w-3 h-3 text-muted-foreground shrink-0" />
                        <span className="truncate flex-1">{t.name}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "mcp" && (
            <div>
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                MCP 服务器 ({member.config.mcps.length})
              </h3>
              {member.config.mcps.length === 0 ? (
                <p className="text-sm text-muted-foreground/60">未配置 MCP 服务器</p>
              ) : (
                <div className="space-y-2">
                  {member.config.mcps.map(m => (
                    <div key={m.name} className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${
                      m.disabled ? "opacity-50" : ""
                    }`}>
                      <Plug className="w-4 h-4 text-muted-foreground shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{m.name}</p>
                        <p className="text-xs text-muted-foreground truncate font-mono">{m.command || "未配置"}</p>
                      </div>
                      <span className={`w-2 h-2 rounded-full ${m.disabled ? "bg-muted-foreground/30" : "bg-success"}`} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Contact Detail ───────────────────────────────────────────────────────

function ContactDetail({ contact, onStartChat }: {
  contact: RelationshipRow;
  onStartChat: () => void;
}) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="flex flex-col items-center max-w-xs">
        <MemberAvatar
          name={contact.peer_name}
          avatarUrl={contact.peer_avatar_url}
          type={contact.peer_type}
          size="lg"
          className="mb-4"
        />

        <h2 className="text-sm font-semibold text-foreground mb-1">{contact.peer_name}</h2>
        <div className="flex items-center gap-1.5 mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-success" />
          <span className="text-xs text-muted-foreground">已添加</span>
        </div>

        <button
          onClick={onStartChat}
          className="w-full py-2 rounded-lg bg-foreground text-background text-sm font-medium hover:bg-foreground/90 transition-colors duration-fast mb-2"
        >
          <MessageSquare className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
          发起对话
        </button>
      </div>
    </div>
  );
}

// ── Group Detail ─────────────────────────────────────────────────────────

function GroupDetail({ group, myEntityId, onEnterChat }: {
  group: GroupInfo;
  myEntityId: string | null;
  onEnterChat: () => void;
}) {
  const name = group.title || group.entities.map(e => e.name).join(", ");

  return (
    <div className="h-full flex items-center justify-center">
      <div className="flex flex-col items-center max-w-sm w-full px-4">
        <GroupAvatar entities={group.entities} />
        <h2 className="text-sm font-semibold text-foreground mt-4 mb-1 text-center">{name}</h2>
        <p className="text-xs text-muted-foreground mb-6">{group.member_count} 位成员</p>

        {/* Member list */}
        <div className="w-full rounded-lg border border-border divide-y divide-border mb-6">
          {group.entities.map(e => (
            <div key={e.id} className="flex items-center gap-2.5 px-3 py-2">
              <MemberAvatar name={e.name} avatarUrl={e.avatar_url} type={e.type} size="xs" />
              <span className="text-sm text-foreground flex-1 truncate">{e.name}</span>
              {e.id === myEntityId && (
                <span className="text-2xs text-muted-foreground">( 我 )</span>
              )}
            </div>
          ))}
        </div>

        <button
          onClick={onEnterChat}
          className="w-full py-2 rounded-lg bg-foreground text-background text-sm font-medium hover:bg-foreground/90 transition-colors duration-fast"
        >
          <MessageSquare className="w-3.5 h-3.5 inline-block mr-1.5 -mt-0.5" />
          进入群聊
        </button>
      </div>
    </div>
  );
}

// ── Empty States ─────────────────────────────────────────────────────────

function EmptyListHint({ text, actionText, onAction }: {
  text: string;
  actionText?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <p className="text-xs text-muted-foreground mb-2">{text}</p>
      {actionText && onAction && (
        <button onClick={onAction} className="text-xs text-primary hover:underline">
          {actionText}
        </button>
      )}
    </div>
  );
}

function DetailEmpty({ text }: { text: string }) {
  return (
    <div className="h-full flex items-center justify-center">
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  );
}
