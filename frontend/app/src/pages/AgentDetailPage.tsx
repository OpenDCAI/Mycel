import { useState, useEffect, useMemo, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Bot, FileText, Wrench, Plug, Zap, Users, BookOpen,
  Tag, Save, Plus, Trash2, Search, X, Check, Lock,
} from "lucide-react";
import PublishDialog from "@/components/PublishDialog";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useAppStore } from "@/store/app-store";
import type { AgentConfig, CrudItem, RuleItem, ResourceItem, SubAgent } from "@/store/types";

// ==================== Types ====================

type ModuleId = "role" | "mcp" | "skills" | "subagents";

interface ModuleDef {
  id: ModuleId;
  label: string;
  icon: typeof FileText;
  count?: (cfg: AgentConfig) => number;
}

const modules: ModuleDef[] = [
  { id: "role", label: "角色", icon: FileText },
  { id: "mcp", label: "MCP", icon: Plug, count: c => c.mcps.length },
  { id: "skills", label: "技能", icon: Zap, count: c => c.skills.length },
  { id: "subagents", label: "子 Agent", icon: Users, count: c => c.subAgents.length },
];

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// ==================== Main Component ====================

export default function AgentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [showPublish, setShowPublish] = useState(false);
  const [activeModule, setActiveModule] = useState<ModuleId>("role");

  const agent = useAppStore(s => s.getAgentById(id || ""));
  const fetchAgent = useAppStore(s => s.fetchAgent);
  const updateAgent = useAppStore(s => s.updateAgent);
  const updateAgentConfig = useAppStore(s => s.updateAgentConfig);
  const librarySkills = useAppStore(s => s.librarySkills);
  const libraryMcps = useAppStore(s => s.libraryMcps);
  const libraryAgents = useAppStore(s => s.libraryAgents);

  const [pickerType, setPickerType] = useState<"skill" | "mcp" | "agent" | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [loadFailure, setLoadFailure] = useState<{ id: string; message: string } | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!id || agent?.config_loaded) return;
    let cancelled = false;
    fetchAgent(id).catch((err) => {
      if (!cancelled) setLoadFailure({ id, message: errorText(err) });
    });
    return () => {
      cancelled = true;
    };
  }, [agent?.config_loaded, fetchAgent, id]);

  const startRename = () => {
    if (!agent) return;
    setNameDraft(agent.name);
    setEditingName(true);
    setTimeout(() => nameInputRef.current?.select(), 0);
  };
  const commitRename = async () => {
    setEditingName(false);
    const trimmed = nameDraft.trim();
    if (!agent || !trimmed || trimmed === agent.name) return;
    try {
      await updateAgent(agent.id, { name: trimmed });
    } catch (err) { toast.error(`重命名失败：${errorText(err)}`); }
  };

  const statusLabels: Record<string, string> = { active: "在岗", draft: "草稿", inactive: "离线" };
  const loadError = loadFailure && loadFailure.id === id ? loadFailure.message : null;

  if (!agent?.config_loaded) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className={`text-sm ${loadError ? "text-destructive" : "text-muted-foreground"}`}>
          {loadError ? `加载失败：${loadError}` : "加载中..."}
        </p>
      </div>
    );
  }

  const handleToggle = async (mod: string, itemName: string, enabled: boolean) => {
    if (!agent) return;
    try {
      if (mod === "tools") {
        await updateAgentConfig(agent.id, { tools: agent.config.tools.map(i => i.name === itemName ? { ...i, enabled } : i) });
      } else if (mod === "mcp") {
        await updateAgentConfig(agent.id, { mcps: agent.config.mcps.map(i => i.name === itemName ? { ...i, disabled: !enabled } : i) });
      } else if (mod === "skills") {
        await updateAgentConfig(agent.id, { skills: agent.config.skills.map(i => i.name === itemName ? { ...i, enabled } : i) });
      }
    } catch (err) { toast.error(`更新失败：${errorText(err)}`); }
  };

  const handleAssign = async (type: "skill" | "mcp" | "agent", names: string[]) => {
    if (!agent) return;
    try {
      if (type === "skill") {
        const existing = new Set(agent.config.skills.map(s => s.name));
        const newSkills = names.filter(n => !existing.has(n)).map(n => {
          const lib = librarySkills.find(s => s.name === n);
          return { name: n, desc: lib?.desc || "", enabled: true };
        });
        if (newSkills.length) await updateAgentConfig(agent.id, { skills: [...agent.config.skills, ...newSkills] });
      } else if (type === "mcp") {
        const existing = new Set(agent.config.mcps.map(m => m.name));
        const newMcps = names.filter(n => !existing.has(n)).map(n => {
          const lib = libraryMcps.find(m => m.name === n);
          return { name: n, command: lib?.desc || "", args: [], env: {}, disabled: false };
        });
        if (newMcps.length) await updateAgentConfig(agent.id, { mcps: [...agent.config.mcps, ...newMcps] });
      } else {
        const existing = new Set(agent.config.subAgents.map(a => a.name));
        const newAgents = names.filter(n => !existing.has(n)).map(n => {
          const lib = libraryAgents.find(a => a.name === n);
          return { name: n, desc: lib?.desc || "", tools: [] as CrudItem[], system_prompt: "" };
        });
        if (newAgents.length) await updateAgentConfig(agent.id, { subAgents: [...agent.config.subAgents, ...newAgents] });
      }
      toast.success("已添加");
    } catch (err) { toast.error(`添加失败：${errorText(err)}`); }
  };

  const handleRemove = async (mod: string, itemName: string) => {
    if (!agent) return;
    try {
      if (mod === "mcp") await updateAgentConfig(agent.id, { mcps: agent.config.mcps.filter(i => i.name !== itemName) });
      else if (mod === "skills") await updateAgentConfig(agent.id, { skills: agent.config.skills.filter(i => i.name !== itemName) });
      else if (mod === "subagents") await updateAgentConfig(agent.id, { subAgents: agent.config.subAgents.filter(i => i.name !== itemName) });
      else if (mod === "rules") await updateAgentConfig(agent.id, { rules: agent.config.rules.filter(i => i.name !== itemName) });
      toast.success("已移除");
    } catch (err) { toast.error(`移除失败：${errorText(err)}`); }
  };

  const renderContent = () => {
    switch (activeModule) {
      case "role":
        return (
          <RolePanel
            prompt={agent.config.prompt || ""}
            tools={agent.config.tools}
            rules={agent.config.rules}
            memory={agent.config.memory}
            onSavePrompt={async (val) => {
              await updateAgentConfig(agent.id, { prompt: val });
              toast.success("System Prompt 已保存");
            }}
            onSaveMemory={async (triggerTokens) => {
              await updateAgentConfig(agent.id, { memory: { compaction: { trigger_tokens: triggerTokens } } });
              toast.success("压缩设置已保存");
            }}
            onToggleTool={(name, en) => handleToggle("tools", name, en)}
            onSaveRule={async (name, content) => {
              await updateAgentConfig(agent.id, { rules: agent.config.rules.map(r => r.name === name ? { ...r, content } : r) });
              toast.success("规则已保存");
            }}
            onAddRule={async (name) => {
              await updateAgentConfig(agent.id, { rules: [...agent.config.rules, { name, content: "" }] });
              toast.success(`${name} 已添加`);
            }}
            onDeleteRule={(name) => handleRemove("rules", name)}
          />
        );
      case "skills":
        return (
          <ResourceCards
            type="skill"
            items={agent.config.skills.map(s => ({ name: s.name, desc: s.desc, enabled: s.enabled }))}
            onToggle={(name, en) => handleToggle("skills", name, en)}
            onRemove={(name) => handleRemove("skills", name)}
            onAdd={() => setPickerType("skill")}
          />
        );
      case "mcp":
        return (
          <ResourceCards
            type="mcp"
            items={agent.config.mcps.map(m => ({ name: m.name, desc: m.command || "未配置", enabled: !m.disabled }))}
            onToggle={(name, en) => handleToggle("mcp", name, en)}
            onRemove={(name) => handleRemove("mcp", name)}
            onAdd={() => setPickerType("mcp")}
          />
        );
      case "subagents":
        return (
          <SubAgentsPanel
            agents={agent.config.subAgents}
            onSave={async (updated) => {
              await updateAgentConfig(agent.id, { subAgents: updated });
              toast.success("Agent 配置已保存");
            }}
            onAdd={() => setPickerType("agent")}
            onDelete={(name) => handleRemove("subagents", name)}
          />
        );
      default: return null;
    }
  };
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b shrink-0">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
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
          <span className="font-medium cursor-pointer hover:underline decoration-dashed underline-offset-4" onDoubleClick={startRename}>{agent.name}</span>
        )}
        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
          {statusLabels[agent.status] || agent.status}
        </span>
        <span className="text-xs text-muted-foreground">v{agent.version}</span>
        <div className="flex-1" />
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
            const count = m.count ? m.count(agent.config) : undefined;
            const active = activeModule === m.id;
            return (
              <button
                key={m.id}
                onClick={() => setActiveModule(m.id)}
                className={`w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors duration-fast ${
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

      {showPublish && <PublishDialog open={showPublish} onOpenChange={setShowPublish} agentId={agent.id} />}
      {pickerType && (() => {
        const libraryMap = { skill: librarySkills, mcp: libraryMcps, agent: libraryAgents };
        const assignedMap = {
          skill: agent.config.skills.map(s => s.name),
          mcp: agent.config.mcps.map(m => m.name),
          agent: agent.config.subAgents.map(a => a.name),
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

function RolePanel({ prompt, tools, rules, memory, onSavePrompt, onSaveMemory, onToggleTool, onSaveRule, onAddRule, onDeleteRule }: {
  prompt: string;
  tools: CrudItem[];
  rules: RuleItem[];
  memory?: AgentConfig["memory"];
  onSavePrompt: (v: string) => Promise<void>;
  onSaveMemory: (triggerTokens: number | null) => Promise<void>;
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
  const triggerTokens = memory?.compaction?.trigger_tokens ?? null;
  const [triggerDraft, setTriggerDraft] = useState(triggerTokens?.toString() ?? "");
  const [savingMemory, setSavingMemory] = useState(false);

  const promptDirty = promptText !== prompt;
  useEffect(() => { setPromptText(prompt); }, [prompt]);
  useEffect(() => { setTriggerDraft(triggerTokens?.toString() ?? ""); }, [triggerTokens]);

  const savePrompt = async () => {
    setSavingPrompt(true);
    try { await onSavePrompt(promptText); } finally { setSavingPrompt(false); }
  };

  const parsedTrigger = triggerDraft.trim() ? Number(triggerDraft) : null;
  const triggerValid = parsedTrigger === null || (Number.isInteger(parsedTrigger) && parsedTrigger > 0);
  const memoryDirty = (parsedTrigger ?? null) !== triggerTokens;

  const saveMemory = async () => {
    if (!triggerValid) return;
    setSavingMemory(true);
    try { await onSaveMemory(parsedTrigger); } finally { setSavingMemory(false); }
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
          <h3 className="text-sm font-medium">系统提示词</h3>
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

      {/* Section 2: Memory */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">上下文压缩</h3>
          <div className="flex-1" />
          <Button size="sm" className="h-7" disabled={!memoryDirty || !triggerValid || savingMemory} onClick={saveMemory}>
            <Save className="h-3.5 w-3.5 mr-1" /> {savingMemory ? "..." : "保存压缩设置"}
          </Button>
        </div>
        <div className="rounded-md border bg-card px-3 py-3">
          <label htmlFor="memory-compaction-trigger" className="text-xs font-medium text-muted-foreground">
            压缩触发 Token
          </label>
          <Input
            id="memory-compaction-trigger"
            className="mt-2 max-w-xs"
            type="number"
            min={1}
            step={1000}
            value={triggerDraft}
            onChange={e => setTriggerDraft(e.target.value)}
            placeholder="留空使用模型上下文自动阈值"
          />
          <p className="mt-2 text-xs text-muted-foreground">
            达到该 Token 数后开始压缩旧上下文；留空时使用模型上下文自动阈值。
          </p>
          {!triggerValid && <p className="mt-2 text-xs text-destructive">请输入正整数，或留空。</p>}
        </div>
      </section>

      {/* Section 3: Tools */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <Wrench className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">工具</h3>
          <span className="text-xs text-muted-foreground">{tools.filter(t => t.enabled).length}/{tools.length}</span>
          <div className="flex-1" />
          <div className="relative w-40">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
            <Input className="pl-7 h-7 text-xs" placeholder="搜索工具..." value={toolFilter} onChange={e => setToolFilter(e.target.value)} />
          </div>
        </div>
        {toolGroups.map(([group, items]) => (
          <div key={group}>
            <p className="text-2xs font-medium text-muted-foreground uppercase mb-1">{group}</p>
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

      {/* Section 4: Rules */}
      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-medium">规则</h3>
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
        className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-muted/50 transition-colors duration-fast"
      >
        <BookOpen className="h-3 w-3 text-muted-foreground shrink-0" />
        <span className="font-medium truncate flex-1 text-left">{rule.name}</span>
        {dirty && <span className="text-2xs text-primary">未保存</span>}
        <span className="text-muted-foreground text-2xs">{expanded ? "收起" : "展开"}</span>
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
          <span className="text-xs font-medium text-muted-foreground">子 Agent</span>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onAdd} title="添加 Agent">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="flex-1 overflow-auto">
          {/* Builtin agents section */}
          {builtinAgents.length > 0 && (
            <div className="py-1">
              <p className="px-3 py-1 text-2xs font-medium text-muted-foreground uppercase tracking-wider">内置</p>
              {builtinAgents.map(a => (
                <button
                  key={a.name}
                  onClick={() => setSelected(a.name)}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs transition-colors duration-fast ${
                    selected === a.name
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted/50"
                  }`}
                >
                  <Lock className="h-3 w-3 shrink-0 opacity-40" />
                  <span className="truncate flex-1 text-left">{a.name}</span>
                  <span className="text-2xs opacity-40">{enabledToolCount(a)}/{a.tools.length}</span>
                </button>
              ))}
            </div>
          )}
          {/* Custom agents section */}
          {(customAgents.length > 0 || builtinAgents.length > 0) && (
            <div className="py-1">
              {builtinAgents.length > 0 && (
                <p className="px-3 py-1 text-2xs font-medium text-muted-foreground uppercase tracking-wider">自定义</p>
              )}
              {customAgents.length === 0 ? (
                <p className="px-3 py-2 text-2xs text-muted-foreground/60">点击 + 添加</p>
              ) : (
                customAgents.map(a => (
                  <button
                    key={a.name}
                    onClick={() => setSelected(a.name)}
                    className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs group transition-colors duration-fast ${
                      selected === a.name
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-muted/50"
                    }`}
                  >
                    <Bot className="h-3 w-3 shrink-0" />
                    <span className="truncate flex-1 text-left">{a.name}</span>
                    <span
                      className="opacity-0 group-hover:opacity-100 shrink-0 text-muted-foreground hover:text-destructive transition-opacity duration-fast"
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
                <span className="text-2xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">只读</span>
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
              <label className="text-xs font-medium text-muted-foreground">描述</label>
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
              <label className="text-xs font-medium text-muted-foreground">系统提示词</label>
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
        <label className="text-xs font-medium text-muted-foreground">工具</label>
        <span className="text-xs text-muted-foreground">{enabledCount}/{items.length} 启用</span>
        <div className="flex-1" />
        <div className="relative w-40">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <Input className="pl-7 h-7 text-xs" placeholder="搜索..." value={filter} onChange={e => setFilter(e.target.value)} />
        </div>
      </div>
      {groups.map(([group, tools]) => (
        <div key={group}>
          <p className="text-2xs font-medium text-muted-foreground uppercase mb-1">{group}</p>
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
  const labels = { skill: "技能", mcp: "MCP 服务器", agent: "子 Agent" };
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
            <button onClick={onAdd} className="hover:text-primary transition-colors duration-fast">
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
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-left transition-colors duration-fast ${
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
