import { useState, useEffect, useMemo, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Bot, FileText, Wrench, Plug, Zap, Users, BookOpen,
  Play, Tag, Save, Plus, Trash2, Search, X, Check, Lock, HardDrive,
} from "lucide-react";
import TestPanel from "@/components/TestPanel";
import PublishDialog from "@/components/PublishDialog";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAppStore } from "@/store/app-store";
import type { CrudItem, RuleItem, ResourceItem, SubAgent } from "@/store/types";

// ==================== Types ====================

interface WorkplaceItem {
  member_name: string;
  provider_type: string;
  backend_ref: string;
  mount_path: string;
  created_at?: string;
}

type ModuleId = "role" | "mcp" | "skills" | "subagents" | "workplace";

interface ModuleDef {
  id: ModuleId;
  label: string;
  icon: typeof FileText;
  count?: (cfg: any) => number;
}

const modules: ModuleDef[] = [
  { id: "role", label: "Role", icon: FileText },
  { id: "mcp", label: "MCP", icon: Plug, count: c => c.mcps.length },
  { id: "skills", label: "Skills", icon: Zap, count: c => c.skills.length },
  { id: "subagents", label: "Agents", icon: Users, count: c => c.subAgents.length },
  { id: "workplace", label: "Workplace", icon: HardDrive },
];

// ==================== Main Component ====================

export default function AgentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [showTest, setShowTest] = useState(false);
  const [showPublish, setShowPublish] = useState(false);
  const [activeModule, setActiveModule] = useState<ModuleId>("role");

  const member = useAppStore(s => s.getMemberById(id || ""));
  const updateMember = useAppStore(s => s.updateMember);
  const updateMemberConfig = useAppStore(s => s.updateMemberConfig);
  const loadAll = useAppStore(s => s.loadAll);
  const librarySkills = useAppStore(s => s.librarySkills);
  const libraryMcps = useAppStore(s => s.libraryMcps);
  const libraryAgents = useAppStore(s => s.libraryAgents);
  useEffect(() => { loadAll(); }, [loadAll]);

  const [pickerType, setPickerType] = useState<"skill" | "mcp" | "agent" | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

  const startRename = () => {
    if (!member) return;
    setNameDraft(member.name);
    setEditingName(true);
    setTimeout(() => nameInputRef.current?.select(), 0);
  };
  const commitRename = async () => {
    setEditingName(false);
    const trimmed = nameDraft.trim();
    if (!member || !trimmed || trimmed === member.name) return;
    try {
      await updateMember(member.id, { name: trimmed });
    } catch { toast.error("重命名失败"); }
  };

  const [workplaces, setWorkplaces] = useState<WorkplaceItem[]>([]);
  useEffect(() => {
    if (member) {
      fetch(`/api/panel/members/${member.id}/workplaces`)
        .then(r => r.json())
        .then(d => setWorkplaces(d.items || []))
        .catch(() => setWorkplaces([]));
    }
  }, [member?.id]);

  const statusLabels: Record<string, string> = { active: "在岗", draft: "草稿", inactive: "离线" };

  if (!member) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    );
  }

  const handleToggle = async (mod: string, itemName: string, enabled: boolean) => {
    if (!member) return;
    try {
      if (mod === "tools") {
        await updateMemberConfig(member.id, { tools: member.config.tools.map(i => i.name === itemName ? { ...i, enabled } : i) });
      } else if (mod === "mcp") {
        await updateMemberConfig(member.id, { mcps: member.config.mcps.map(i => i.name === itemName ? { ...i, disabled: !enabled } : i) });
      } else if (mod === "skills") {
        await updateMemberConfig(member.id, { skills: member.config.skills.map(i => i.name === itemName ? { ...i, enabled } : i) });
      }
    } catch { toast.error("更新失败"); }
  };

  const handleAssign = async (type: "skill" | "mcp" | "agent", names: string[]) => {
    if (!member) return;
    try {
      if (type === "skill") {
        const existing = new Set(member.config.skills.map(s => s.name));
        const newSkills = names.filter(n => !existing.has(n)).map(n => {
          const lib = librarySkills.find(s => s.name === n);
          return { name: n, desc: lib?.desc || "", enabled: true };
        });
        if (newSkills.length) await updateMemberConfig(member.id, { skills: [...member.config.skills, ...newSkills] });
      } else if (type === "mcp") {
        const existing = new Set(member.config.mcps.map(m => m.name));
        const newMcps = names.filter(n => !existing.has(n)).map(n => {
          const lib = libraryMcps.find(m => m.name === n);
          return { name: n, command: lib?.desc || "", args: [], env: {}, disabled: false };
        });
        if (newMcps.length) await updateMemberConfig(member.id, { mcps: [...member.config.mcps, ...newMcps] });
      } else {
        const existing = new Set(member.config.subAgents.map(a => a.name));
        const newAgents = names.filter(n => !existing.has(n)).map(n => {
          const lib = libraryAgents.find(a => a.name === n);
          return { name: n, desc: lib?.desc || "", tools: [] as CrudItem[], system_prompt: "" };
        });
        if (newAgents.length) await updateMemberConfig(member.id, { subAgents: [...member.config.subAgents, ...newAgents] });
      }
      toast.success("已添加");
    } catch { toast.error("添加失败"); }
  };

  const handleRemove = async (mod: string, itemName: string) => {
    if (!member) return;
    try {
      if (mod === "mcp") await updateMemberConfig(member.id, { mcps: member.config.mcps.filter(i => i.name !== itemName) });
      else if (mod === "skills") await updateMemberConfig(member.id, { skills: member.config.skills.filter(i => i.name !== itemName) });
      else if (mod === "subagents") await updateMemberConfig(member.id, { subAgents: member.config.subAgents.filter(i => i.name !== itemName) });
      else if (mod === "rules") await updateMemberConfig(member.id, { rules: member.config.rules.filter(i => i.name !== itemName) });
      toast.success("已移除");
    } catch { toast.error("移除失败"); }
  };

  const renderContent = () => {
    switch (activeModule) {
      case "role":
        return (
          <RolePanel
            prompt={member.config.prompt || ""}
            tools={member.config.tools}
            rules={member.config.rules}
            onSavePrompt={async (val) => {
              await updateMemberConfig(member.id, { prompt: val });
              toast.success("System Prompt 已保存");
            }}
            onToggleTool={(name, en) => handleToggle("tools", name, en)}
            onSaveRule={async (name, content) => {
              await updateMemberConfig(member.id, { rules: member.config.rules.map(r => r.name === name ? { ...r, content } : r) });
              toast.success("规则已保存");
            }}
            onAddRule={async (name) => {
              await updateMemberConfig(member.id, { rules: [...member.config.rules, { name, content: "" }] });
              toast.success(`${name} 已添加`);
            }}
            onDeleteRule={(name) => handleRemove("rules", name)}
          />
        );
      case "skills":
        return (
          <ResourceCards
            type="skill"
            items={member.config.skills.map(s => ({ name: s.name, desc: s.desc, enabled: s.enabled }))}
            onToggle={(name, en) => handleToggle("skills", name, en)}
            onRemove={(name) => handleRemove("skills", name)}
            onAdd={() => setPickerType("skill")}
          />
        );
      case "mcp":
        return (
          <ResourceCards
            type="mcp"
            items={member.config.mcps.map(m => ({ name: m.name, desc: m.command || "未配置", enabled: !m.disabled }))}
            onToggle={(name, en) => handleToggle("mcp", name, en)}
            onRemove={(name) => handleRemove("mcp", name)}
            onAdd={() => setPickerType("mcp")}
          />
        );
      case "subagents":
        return (
          <SubAgentsPanel
            agents={member.config.subAgents}
            onSave={async (updated) => {
              await updateMemberConfig(member.id, { subAgents: updated });
              toast.success("Agent 配置已保存");
            }}
            onAdd={() => setPickerType("agent")}
            onDelete={(name) => handleRemove("subagents", name)}
          />
        );
      case "workplace":
        return <WorkplacePanel items={workplaces} />;
      default: return null;
    }
  };
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b shrink-0">
        <Button variant="ghost" size="icon" onClick={() => navigate("/members")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <Bot className="h-5 w-5 text-primary" />
        {editingName ? (
          <input
            ref={nameInputRef}
            className="font-medium bg-transparent border-b border-primary outline-none px-0 py-0 text-sm w-48"
            value={nameDraft}
            onChange={e => setNameDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={e => { if (e.key === "Enter") commitRename(); if (e.key === "Escape") setEditingName(false); }}
          />
        ) : (
          <span className="font-medium cursor-pointer hover:underline decoration-dashed underline-offset-4" onDoubleClick={startRename}>{member.name}</span>
        )}
        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
          {statusLabels[member.status] || member.status}
        </span>
        <span className="text-xs text-muted-foreground">v{member.version}</span>
        <div className="flex-1" />
        <Button size="sm" variant="outline" onClick={() => setShowTest(true)}>
          <Play className="h-3.5 w-3.5 mr-1" /> 测试
        </Button>
        <Button size="sm" onClick={() => setShowPublish(true)}>
          <Tag className="h-3.5 w-3.5 mr-1" /> 发布
        </Button>
      </div>

      {/* Body: sidebar + content */}
      <div className="flex-1 flex min-h-0">
        {/* Flat sidebar */}
        <nav className="w-48 shrink-0 border-r bg-muted/30 py-2">
          {modules.map(m => {
            const Icon = m.icon;
            const count = m.id === "workplace" ? workplaces.length : (m.count ? m.count(member.config) : undefined);
            const active = activeModule === m.id;
            return (
              <button
                key={m.id}
                onClick={() => setActiveModule(m.id)}
                className={`w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors ${
                  active ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:bg-muted"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{m.label}</span>
                {count !== undefined && (
                  <span className="ml-auto text-xs opacity-60">{count}</span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Content */}
        <div className="flex-1 min-w-0 overflow-auto">
          {renderContent()}
        </div>
      </div>

      {showTest && <TestPanel memberName={member.name} onClose={() => setShowTest(false)} />}
      {showPublish && <PublishDialog open={showPublish} onOpenChange={setShowPublish} memberId={member.id} />}
      {pickerType && (() => {
        const libraryMap = { skill: librarySkills, mcp: libraryMcps, agent: libraryAgents };
        const assignedMap = {
          skill: member.config.skills.map(s => s.name),
          mcp: member.config.mcps.map(m => m.name),
          agent: member.config.subAgents.map(a => a.name),
        };
        return (
          <ResourcePicker
            type={pickerType}
            library={libraryMap[pickerType]}
            assigned={assignedMap[pickerType]}
            onConfirm={(names) => { handleAssign(pickerType, names); setPickerType(null); }}
            onClose={() => setPickerType(null)}
          />
        );
      })()}
    </div>
  );
}

// ==================== RolePanel (Prompt + Tools + Rules) ====================

function RolePanel({ prompt, tools, rules, onSavePrompt, onToggleTool, onSaveRule, onAddRule, onDeleteRule }: {
  prompt: string;
  tools: CrudItem[];
  rules: RuleItem[];
  onSavePrompt: (v: string) => Promise<void>;
  onToggleTool: (name: string, enabled: boolean) => void;
  onSaveRule: (name: string, content: string) => Promise<void>;
  onAddRule: (name: string) => Promise<void>;
  onDeleteRule: (name: string) => void;
}) {
  const [promptText, setPromptText] = useState(prompt);
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [toolFilter, setToolFilter] = useState("");
  const [addRuleOpen, setAddRuleOpen] = useState(false);
  const [addRuleName, setAddRuleName] = useState("");

  const promptDirty = promptText !== prompt;
  useEffect(() => { setPromptText(prompt); }, [prompt]);

  const savePrompt = async () => {
    setSavingPrompt(true);
    try { await onSavePrompt(promptText); } finally { setSavingPrompt(false); }
  };

  const toolGroups = useMemo(() => {
    const map: Record<string, CrudItem[]> = {};
    for (const t of tools) {
      if (toolFilter && !t.name.toLowerCase().includes(toolFilter.toLowerCase())) continue;
      const g = t.group || "other";
      (map[g] ??= []).push(t);
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [tools, toolFilter]);

  const doAddRule = async () => {
    const n = addRuleName.trim();
    if (!n) return;
    await onAddRule(n.endsWith(".md") ? n : `${n}.md`);
    setAddRuleName("");
    setAddRuleOpen(false);
  };

  return (
    <div className="p-4 space-y-6 overflow-auto">
      {/* Section 1: System Prompt */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">System Prompt</h3>
          <div className="flex-1" />
          <Button size="sm" className="h-7" disabled={!promptDirty || savingPrompt} onClick={savePrompt}>
            <Save className="h-3.5 w-3.5 mr-1" /> {savingPrompt ? "..." : "保存"}
          </Button>
        </div>
        <textarea
          className="w-full h-40 rounded-md border bg-background px-3 py-2 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-ring"
          value={promptText}
          onChange={e => setPromptText(e.target.value)}
          placeholder="输入 System Prompt..."
        />
      </section>

      {/* Section 2: Tools */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <Wrench className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">Tools</h3>
          <span className="text-xs text-muted-foreground">{tools.filter(t => t.enabled).length}/{tools.length}</span>
          <div className="flex-1" />
          <div className="relative w-40">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
            <Input className="pl-7 h-7 text-xs" placeholder="搜索工具..." value={toolFilter} onChange={e => setToolFilter(e.target.value)} />
          </div>
        </div>
        {toolGroups.map(([group, items]) => (
          <div key={group}>
            <p className="text-[10px] font-medium text-muted-foreground uppercase mb-1">{group}</p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-1.5">
              {items.map(t => (
                <div key={t.name} className="flex items-center gap-1.5 rounded border px-2 py-1.5 text-xs">
                  <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
                  <span className="truncate flex-1" title={t.desc}>{t.name}</span>
                  <Switch checked={t.enabled} onCheckedChange={v => onToggleTool(t.name, v)} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      {/* Section 3: Rules */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">Rules</h3>
          <span className="text-xs text-muted-foreground">{rules.length} 个文件</span>
          <div className="flex-1" />
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setAddRuleOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        {rules.length === 0 ? (
          <p className="text-xs text-muted-foreground py-2">暂无规则文件，点击 + 添加</p>
        ) : (
          <div className="space-y-2">
            {rules.map(r => (
              <RuleEditor key={r.name} rule={r} onSave={onSaveRule} onDelete={onDeleteRule} />
            ))}
          </div>
        )}
      </section>

      {/* Add rule dialog */}
      <Dialog open={addRuleOpen} onOpenChange={setAddRuleOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>添加规则文件</DialogTitle><DialogDescription className="sr-only">输入规则文件名称以添加新规则</DialogDescription></DialogHeader>
          <Input placeholder="文件名，如 coding.md" value={addRuleName} onChange={e => setAddRuleName(e.target.value)} onKeyDown={e => e.key === "Enter" && doAddRule()} />
          <DialogFooter><Button size="sm" onClick={doAddRule} disabled={!addRuleName.trim()}>添加</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ==================== RuleEditor (collapsible) ====================

function RuleEditor({ rule, onSave, onDelete }: {
  rule: RuleItem;
  onSave: (name: string, content: string) => Promise<void>;
  onDelete: (name: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [text, setText] = useState(rule.content);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setText(rule.content); }, [rule.content]);

  const dirty = text !== rule.content;

  const save = async () => {
    setSaving(true);
    try { await onSave(rule.name, text); } finally { setSaving(false); }
  };

  return (
    <div className="rounded-md border">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-muted/50 transition-colors"
      >
        <BookOpen className="h-3 w-3 text-muted-foreground shrink-0" />
        <span className="font-medium truncate flex-1 text-left">{rule.name}</span>
        {dirty && <span className="text-[10px] text-primary">未保存</span>}
        <span className="text-muted-foreground text-[10px]">{expanded ? "收起" : "展开"}</span>
      </button>
      {expanded && (
        <div className="border-t px-3 py-2 space-y-2">
          <textarea
            className="w-full h-32 rounded-md border bg-background px-3 py-2 text-xs font-mono resize-y focus:outline-none focus:ring-2 focus:ring-ring"
            value={text}
            onChange={e => setText(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" className="h-6 text-xs text-destructive" onClick={() => onDelete(rule.name)}>
              <Trash2 className="h-3 w-3 mr-1" /> 删除
            </Button>
            <Button size="sm" className="h-6 text-xs" disabled={!dirty || saving} onClick={save}>
              <Save className="h-3 w-3 mr-1" /> {saving ? "..." : "保存"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ==================== SubAgentsPanel ====================

function SubAgentsPanel({ agents, onSave, onAdd, onDelete }: {
  agents: SubAgent[];
  onSave: (updated: SubAgent[]) => Promise<void>;
  onAdd: () => void;
  onDelete: (name: string) => void;
}) {
  const builtinAgents = useMemo(() => agents.filter(a => a.builtin), [agents]);
  const customAgents = useMemo(() => agents.filter(a => !a.builtin), [agents]);

  const [selected, setSelected] = useState<string | null>(agents[0]?.name ?? null);
  const [draft, setDraft] = useState<SubAgent | null>(null);
  const [saving, setSaving] = useState(false);

  const current = agents.find(a => a.name === selected);
  const isBuiltin = current?.builtin;

  useEffect(() => {
    if (current) {
      setDraft({ ...current, tools: current.tools.map(t => ({ ...t })) });
    } else {
      setDraft(null);
    }
  }, [current]);

  const dirty = useMemo(() => {
    if (!current || !draft || isBuiltin) return false;
    if (draft.desc !== current.desc) return true;
    if (draft.system_prompt !== current.system_prompt) return true;
    if (draft.tools.length !== current.tools.length) return true;
    return draft.tools.some((t, i) => t.enabled !== current.tools[i]?.enabled);
  }, [current, draft, isBuiltin]);

  const save = async () => {
    if (!draft || !selected || isBuiltin) return;
    setSaving(true);
    try {
      const updated = agents.map(a => a.name === selected ? draft : a);
      await onSave(updated);
    } finally {
      setSaving(false);
    }
  };

  const handleToolToggle = (toolName: string, enabled: boolean) => {
    if (!draft || isBuiltin) return;
    setDraft({ ...draft, tools: draft.tools.map(t => t.name === toolName ? { ...t, enabled } : t) });
  };

  const enabledToolCount = (a: SubAgent) => a.tools.filter(t => t.enabled).length;

  return (
    <div className="h-full flex">
      {/* Sidebar */}
      <div className="w-52 shrink-0 border-r flex flex-col">
        <div className="flex items-center justify-between px-3 py-2 border-b">
          <span className="text-xs font-medium text-muted-foreground">Sub-Agents</span>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onAdd} title="添加 Agent">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="flex-1 overflow-auto">
          {/* Builtin agents section */}
          {builtinAgents.length > 0 && (
            <div className="py-1">
              <p className="px-3 py-1 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">内置</p>
              {builtinAgents.map(a => (
                <button
                  key={a.name}
                  onClick={() => setSelected(a.name)}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs transition-colors ${
                    selected === a.name
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted/50"
                  }`}
                >
                  <Lock className="h-3 w-3 shrink-0 opacity-40" />
                  <span className="truncate flex-1 text-left">{a.name}</span>
                  <span className="text-[10px] opacity-40">{enabledToolCount(a)}/{a.tools.length}</span>
                </button>
              ))}
            </div>
          )}
          {/* Custom agents section */}
          {(customAgents.length > 0 || builtinAgents.length > 0) && (
            <div className="py-1">
              {builtinAgents.length > 0 && (
                <p className="px-3 py-1 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">自定义</p>
              )}
              {customAgents.length === 0 ? (
                <p className="px-3 py-2 text-[10px] text-muted-foreground/60">点击 + 添加</p>
              ) : (
                customAgents.map(a => (
                  <button
                    key={a.name}
                    onClick={() => setSelected(a.name)}
                    className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs group transition-colors ${
                      selected === a.name
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-muted/50"
                    }`}
                  >
                    <Bot className="h-3 w-3 shrink-0" />
                    <span className="truncate flex-1 text-left">{a.name}</span>
                    <span
                      className="opacity-0 group-hover:opacity-100 shrink-0 text-muted-foreground hover:text-destructive transition-opacity"
                      onClick={e => { e.stopPropagation(); onDelete(a.name); setSelected(agents.find(x => x.name !== a.name)?.name ?? null); }}
                    >
                      <X className="h-3 w-3" />
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 flex flex-col min-w-0 overflow-auto">
        {draft ? (
          <div className="flex flex-col gap-4 p-4">
            {/* Header */}
            <div className="flex items-center gap-2">
              {isBuiltin ? <Lock className="h-4 w-4 text-muted-foreground" /> : <Bot className="h-4 w-4 text-muted-foreground" />}
              <span className="text-sm font-medium">{draft.name}</span>
              {isBuiltin && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">只读</span>
              )}
              <div className="flex-1" />
              {!isBuiltin && (
                <Button size="sm" className="h-7" disabled={!dirty || saving} onClick={save}>
                  <Save className="h-3.5 w-3.5 mr-1" /> {saving ? "..." : "保存"}
                </Button>
              )}
            </div>

            {/* Description */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Description</label>
              {isBuiltin ? (
                <p className="text-sm text-foreground/80 px-1">{draft.desc || "—"}</p>
              ) : (
                <Input
                  value={draft.desc}
                  onChange={e => setDraft({ ...draft, desc: e.target.value })}
                  placeholder="Agent 描述..."
                  className="h-8 text-sm"
                />
              )}
            </div>

            {/* System Prompt */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">System Prompt</label>
              {isBuiltin ? (
                <pre className="w-full max-h-48 overflow-auto rounded-md border bg-muted/30 px-3 py-2 text-xs font-mono text-foreground/70 whitespace-pre-wrap">
                  {draft.system_prompt || "—"}
                </pre>
              ) : (
                <textarea
                  className="w-full h-32 rounded-md border bg-background px-3 py-2 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                  value={draft.system_prompt}
                  onChange={e => setDraft({ ...draft, system_prompt: e.target.value })}
                  placeholder="输入 System Prompt..."
                />
              )}
            </div>

            {/* Tools */}
            {draft.tools.length > 0 && (
              <SubAgentToolsGrid items={draft.tools} onToggle={handleToolToggle} readOnly={!!isBuiltin} />
            )}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
            选择一个 Agent 查看详情
          </div>
        )}
      </div>
    </div>
  );
}

// ==================== SubAgentToolsGrid (compact) ====================

function SubAgentToolsGrid({ items, onToggle, readOnly = false }: {
  items: CrudItem[];
  onToggle: (name: string, enabled: boolean) => void;
  readOnly?: boolean;
}) {
  const [filter, setFilter] = useState("");
  const groups = useMemo(() => {
    const map: Record<string, CrudItem[]> = {};
    for (const t of items) {
      if (filter && !t.name.toLowerCase().includes(filter.toLowerCase())) continue;
      const g = t.group || "other";
      (map[g] ??= []).push(t);
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [items, filter]);

  const enabledCount = items.filter(t => t.enabled).length;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-muted-foreground">Tools</label>
        <span className="text-xs text-muted-foreground">{enabledCount}/{items.length} 启用</span>
        <div className="flex-1" />
        <div className="relative w-40">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <Input className="pl-7 h-7 text-xs" placeholder="搜索..." value={filter} onChange={e => setFilter(e.target.value)} />
        </div>
      </div>
      {groups.map(([group, tools]) => (
        <div key={group}>
          <p className="text-[10px] font-medium text-muted-foreground uppercase mb-1">{group}</p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5">
            {tools.map(t => (
              <div key={t.name} className={`flex items-center gap-1.5 rounded border px-2 py-1.5 text-xs ${readOnly ? "opacity-60" : ""}`}>
                <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className="truncate flex-1" title={t.desc}>{t.name}</span>
                <Switch checked={t.enabled} onCheckedChange={v => onToggle(t.name, v)} disabled={readOnly} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ==================== ResourceCards ====================

interface ResourceCardItem {
  name: string;
  desc?: string;
  enabled?: boolean;
}

function ResourceCards({ type, items, onToggle, onRemove, onAdd }: {
  type: "skill" | "mcp" | "agent";
  items: ResourceCardItem[];
  onToggle?: (name: string, enabled: boolean) => void;
  onRemove?: (name: string) => void;
  onAdd?: () => void;
}) {
  const labels = { skill: "Skills", mcp: "MCP Servers", agent: "Agents" };
  const icons = { skill: Zap, mcp: Plug, agent: Users };
  const Icon = icons[type];

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-medium">{labels[type]}</h3>
        <span className="text-xs text-muted-foreground">{items.length} 项</span>
        {onAdd && (
          <Button variant="ghost" size="icon" className="h-6 w-6 ml-auto" onClick={onAdd}>
            <Plus className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
      {items.length === 0 ? (
        <div className="text-sm text-muted-foreground py-8 text-center">
          {onAdd ? (
            <button onClick={onAdd} className="hover:text-primary transition-colors">
              点击 + 从 Library 添加{labels[type]}
            </button>
          ) : (
            <>暂无{labels[type]}</>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
          {items.map(item => (
            <div key={item.name} className="flex items-start gap-2 rounded-md border px-3 py-2.5">
              <Icon className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{item.name}</p>
                {item.desc && <p className="text-xs text-muted-foreground truncate">{item.desc}</p>}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {onToggle && item.enabled !== undefined && (
                  <Switch checked={item.enabled} onCheckedChange={v => onToggle(item.name, v)} />
                )}
                {onRemove && (
                  <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive" onClick={() => onRemove(item.name)}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ==================== ResourcePicker ====================

function ResourcePicker({ type, library, assigned, onConfirm, onClose }: {
  type: "skill" | "mcp" | "agent";
  library: ResourceItem[];
  assigned: string[];
  onConfirm: (names: string[]) => void;
  onClose: () => void;
}) {
  const labels = { skill: "Skill", mcp: "MCP", agent: "Agent" };
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const assignedSet = useMemo(() => new Set(assigned), [assigned]);

  const available = useMemo(() =>
    library.filter(item => !assignedSet.has(item.name) && (!filter || item.name.toLowerCase().includes(filter.toLowerCase()))),
    [library, assignedSet, filter]
  );

  const toggle = (name: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>从 Library 添加 {labels[type]}</DialogTitle>
          <DialogDescription className="sr-only">从资源库中选择要添加的{labels[type]}</DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input className="pl-8 h-8 text-xs" placeholder="搜索..." value={filter} onChange={e => setFilter(e.target.value)} />
        </div>
        <div className="max-h-64 overflow-auto space-y-1">
          {available.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              {library.length === 0 ? "Library 中暂无资源，请先去 Library 创建" : "没有可添加的资源"}
            </p>
          ) : available.map(item => (
            <button
              key={item.id}
              onClick={() => toggle(item.name)}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-left transition-colors ${
                selected.has(item.name) ? "bg-primary/10 text-primary" : "hover:bg-muted"
              }`}
            >
              <div className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                selected.has(item.name) ? "bg-primary border-primary" : "border-muted-foreground/30"
              }`}>
                {selected.has(item.name) && <Check className="h-3 w-3 text-primary-foreground" />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-medium truncate">{item.name}</p>
                {item.desc && <p className="text-xs text-muted-foreground truncate">{item.desc}</p>}
              </div>
            </button>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>取消</Button>
          <Button size="sm" disabled={selected.size === 0} onClick={() => onConfirm([...selected])}>
            添加 {selected.size > 0 && `(${selected.size})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ==================== WorkplacePanel ====================

function WorkplacePanel({ items }: { items: WorkplaceItem[] }) {
  if (!items.length) {
    return (
      <div className="flex items-center justify-center h-40 text-sm text-muted-foreground">
        No workplaces created yet. Start a thread with a remote sandbox to create one.
      </div>
    );
  }
  return (
    <div className="space-y-3 p-4">
      {items.map((wp) => (
        <div key={wp.provider_type} className="rounded-lg border p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-medium text-sm">{wp.provider_type}</span>
            <span className="text-xs text-muted-foreground">
              {wp.created_at ? new Date(wp.created_at).toLocaleString() : ""}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-muted-foreground">Backend Ref: </span>
              <code className="bg-muted px-1 rounded">{wp.backend_ref}</code>
            </div>
            <div>
              <span className="text-muted-foreground">Mount Path: </span>
              <code className="bg-muted px-1 rounded">{wp.mount_path}</code>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
