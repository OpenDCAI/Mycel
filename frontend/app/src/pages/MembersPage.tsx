import { useState, useEffect } from "react";
import { Search, Bot } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { authFetch } from "@/store/auth-store";

interface AgentMember {
  id: string;
  name: string;
  type: string;
  avatar: string | null;
  description: string | null;
  owner_name: string | null;
  is_mine: boolean;
  entities: Array<{ id: string; name: string; type: string }>;
  created_at: number;
}

const avatarColors = [
  "bg-primary/15 text-primary",
  "bg-emerald-100 text-emerald-700",
  "bg-amber-100 text-amber-700",
  "bg-rose-100 text-rose-700",
  "bg-violet-100 text-violet-700",
  "bg-sky-100 text-sky-700",
];

export default function MembersPage() {
  const [members, setMembers] = useState<AgentMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    authFetch("/api/members")
      .then(r => r.json())
      .then((data: AgentMember[]) => { setMembers(data); setLoading(false); })
      .catch((err) => { console.error("[MembersPage] fetch error:", err); setLoading(false); });
  }, []);

  const filtered = search
    ? members.filter(m => m.name.toLowerCase().includes(search.toLowerCase()) || m.owner_name?.toLowerCase().includes(search.toLowerCase()))
    : members;

  // Sort: mine first, then by name
  const sorted = [...filtered].sort((a, b) => {
    if (a.is_mine && !b.is_mine) return -1;
    if (!a.is_mine && b.is_mine) return 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="h-14 flex items-center justify-between px-4 md:px-6 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">Members</h2>
          <span className="text-xs text-muted-foreground font-mono">{members.length}</span>
        </div>
      </div>

      {/* Search */}
      {members.length > 0 && (
        <div className="px-4 md:px-6 py-3 border-b border-border">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search members..."
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors"
            />
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <p className="text-sm text-muted-foreground">Loading...</p>
          </div>
        ) : sorted.length === 0 ? (
          members.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24">
              <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
                <Bot className="w-7 h-7 text-primary" />
              </div>
              <p className="text-sm font-semibold text-foreground mb-1">No members yet</p>
              <p className="text-xs text-muted-foreground max-w-[220px] text-center leading-relaxed">
                Members are created when users register
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-24">
              <p className="text-sm font-medium text-foreground mb-1">No matches</p>
              <p className="text-xs text-muted-foreground">Try a different search term</p>
            </div>
          )
        ) : (
          <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {sorted.map((member, index) => {
              const colorClass = avatarColors[index % avatarColors.length];
              const initials = member.name.split(/[\s']/)[0].charAt(0).toUpperCase();

              return (
                <div
                  key={member.id}
                  className="p-4 rounded-xl border border-border bg-card hover:shadow-md hover:-translate-y-0.5 transition-all cursor-pointer group"
                  onClick={() => navigate(`/members/${member.id}`)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold ${colorClass}`}>
                      {initials}
                    </div>
                    {member.is_mine && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
                        mine
                      </span>
                    )}
                  </div>
                  <h3 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors mb-0.5">
                    {member.name}
                  </h3>
                  <p className="text-xs text-muted-foreground mb-2">
                    {member.owner_name ? `owned by ${member.owner_name}` : ""}
                  </p>
                  {member.description && (
                    <p className="text-xs text-muted-foreground/70 line-clamp-2">{member.description}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
