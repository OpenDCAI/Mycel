import { useState, useEffect } from "react";
import { X, Save, Tag, Users, Calendar, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useAppStore } from "@/store/app-store";
import { formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";
import type { ResourceItem } from "@/store/types";

interface Props {
  item: ResourceItem | null;
  type: "skill" | "mcp" | "agent";
  onClose: () => void;
  onCreated?: (item: ResourceItem) => void;
}

export default function LibraryEditor({ item, type, onClose, onCreated }: Props) {
  const fetchResourceContent = useAppStore(s => s.fetchResourceContent);
  const updateResourceContent = useAppStore(s => s.updateResourceContent);
  const updateResource = useAppStore(s => s.updateResource);
  const addResource = useAppStore(s => s.addResource);
  const getResourceUsedBy = useAppStore(s => s.getResourceUsedBy);

  const isNew = item === null;

  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [desc, setDesc] = useState("");

  // Load existing item data
  useEffect(() => {
    if (!item) {
      setName(""); setDesc("");
      setContent(""); setSavedContent("");
      setLoading(false);
      return;
    }
    setName(item.name);
    setDesc(item.desc);
    setLoading(true);
    fetchResourceContent(type, item.id)
      .then(c => { setContent(c); setSavedContent(c); })
      .catch(() => { setContent(""); setSavedContent(""); })
      .finally(() => setLoading(false));
  }, [item?.id, type, fetchResourceContent]);

  const savedMeta = item ? { name: item.name, desc: item.desc } : null;
  const contentDirty = content !== savedContent;
  const metaDirty = isNew
    ? name.trim().length > 0
    : (desc !== savedMeta!.desc);
  const dirty = contentDirty || metaDirty;
  const canSave = isNew ? name.trim().length > 0 : dirty;

  const usedByMembers = item ? getResourceUsedBy(type, item.name) : [];
  const updatedText = item?.updated_at
    ? formatDistanceToNow(new Date(item.updated_at), { addSuffix: true, locale: zhCN })
    : "";

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        const created = await addResource(type, name.trim(), desc.trim());
        if (content.trim()) await updateResourceContent(type, created.id, content);
        toast.success(`${name.trim()} 已创建`);
        onCreated?.(created);
      } else {
        if (metaDirty) await updateResource(type, item.id, { desc });
        if (contentDirty) await updateResourceContent(type, item.id, content);
        setSavedContent(content);
        toast.success("已保存");
      }
    } catch { toast.error(isNew ? "创建失败" : "保存失败"); }
    finally { setSaving(false); }
  };

  const typeLabel = type === "skill" ? "Skill" : type === "mcp" ? "MCP" : "Agent";
  const fileHint = type === "skill" ? "SKILL.md" : type === "agent" ? `${item?.id || "new"}.md` : ".mcp.json";

  return (
    <div className="w-[420px] shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">
      {/* Header */}
      <div className="h-12 flex items-center justify-between px-4 border-b border-border shrink-0">
        {isNew ? (
          <Input className="h-7 text-sm font-semibold flex-1 mr-2" placeholder="输入名称..." value={name} onChange={e => setName(e.target.value)} autoFocus />
        ) : (
          <h3 className="text-sm font-semibold text-foreground truncate">{item.name}</h3>
        )}
        <div className="flex items-center gap-1.5 shrink-0">
          <Button size="sm" className="h-7" disabled={!canSave || saving} onClick={handleSave}>
            <Save className="h-3.5 w-3.5 mr-1" /> {saving ? "..." : isNew ? "创建" : "保存"}
          </Button>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-muted transition-colors duration-fast">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Meta section */}
        <div className="px-4 py-3 space-y-2 border-b border-border">
          {!isNew && (
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1"><Tag className="w-3 h-3" /> {typeLabel}</span>
              <span className="flex items-center gap-1" title={usedByMembers.length ? usedByMembers.join(", ") : undefined}>
                <Users className="w-3 h-3" /> {usedByMembers.length ? usedByMembers.join(", ") : "未被使用"}
              </span>
              {updatedText && <span className="flex items-center gap-1"><Calendar className="w-3 h-3" /> {updatedText}</span>}
            </div>
          )}
          <div className="space-y-1.5">
            <Input className="h-7 text-xs" placeholder="描述" value={desc} onChange={e => setDesc(e.target.value)} />
          </div>
        </div>

        {/* Content editor */}
        <div className="flex-1 flex flex-col px-4 py-3 gap-2">
          <div className="flex items-center gap-2">
            <FileText className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground font-mono">{fileHint}</span>
          </div>
          {loading ? (
            <div className="flex-1 flex items-center justify-center py-12">
              <p className="text-xs text-muted-foreground">加载中...</p>
            </div>
          ) : (
            <textarea
              className="w-full rounded-md border bg-background px-3 py-2 text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-ring"
              style={{ minHeight: "320px" }}
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder={type === "mcp" ? "MCP 配置 (JSON)..." : "编辑内容..."}
              spellCheck={false}
            />
          )}
        </div>
      </div>
    </div>
  );
}
