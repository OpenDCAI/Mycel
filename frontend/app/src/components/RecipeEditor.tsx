import { useEffect, useMemo, useState } from "react";
import { Box, RotateCcw, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";

import type { RecipeFeatureOption } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/store/app-store";
import type { ResourceItem } from "@/store/types";

interface RecipeEditorProps {
  item: ResourceItem;
  onDeleted?: () => void;
}

function featureOptionsFor(item: ResourceItem): RecipeFeatureOption[] {
  return item.feature_options ?? [];
}

export default function RecipeEditor({ item, onDeleted }: RecipeEditorProps) {
  const updateResource = useAppStore((s) => s.updateResource);
  const deleteResource = useAppStore((s) => s.deleteResource);
  const [name, setName] = useState(item.name);
  const [desc, setDesc] = useState(item.desc);
  const [features, setFeatures] = useState<Record<string, boolean>>(item.features ?? {});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(item.name);
    setDesc(item.desc);
    setFeatures(item.features ?? {});
  }, [item]);

  const dirty = useMemo(() => {
    if (name !== item.name || desc !== item.desc) return true;
    const base = item.features ?? {};
    const keys = new Set([...Object.keys(base), ...Object.keys(features)]);
    return [...keys].some((key) => Boolean(base[key]) !== Boolean(features[key]));
  }, [desc, features, item, name]);

  async function handleSave() {
    setSaving(true);
    try {
      await updateResource("recipe", item.id, { name, desc, features });
      toast.success("Sandbox recipe 已保存");
    } catch (error) {
      toast.error(`保存失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteOrReset() {
    const action = item.builtin ? "重置" : "删除";
    if (!window.confirm(`${action} ${item.name}?`)) return;
    setSaving(true);
    try {
      await deleteResource("recipe", item.id);
      toast.success(item.builtin ? "Sandbox recipe 已重置" : "Sandbox recipe 已删除");
      if (!item.builtin) onDeleted?.();
    } catch (error) {
      toast.error(`${action}失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(false);
    }
  }

  const featureOptions = featureOptionsFor(item);
  const providerLabel = item.provider_name || item.provider_type || "unknown";

  return (
    <section className="rounded-2xl border border-border bg-card overflow-hidden">
      <div className="flex items-start gap-3 border-b border-border px-5 py-4">
        <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
          <Box className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-foreground">{item.name}</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Sandbox · {providerLabel} · {item.builtin ? "默认模板" : "自定义模板"}
          </p>
        </div>
      </div>

      <div className="space-y-5 px-5 py-5">
        <div className="space-y-2">
          <label htmlFor="recipe-name" className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
            Name
          </label>
          <Input id="recipe-name" value={name} onChange={(event) => setName(event.target.value)} />
        </div>

        <div className="space-y-2">
          <label htmlFor="recipe-desc" className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
            Description
          </label>
          <Input id="recipe-desc" value={desc} onChange={(event) => setDesc(event.target.value)} />
        </div>

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Bootstrap Features</div>
          <div className="space-y-2">
            {featureOptions.map((option) => {
              const checked = Boolean(features[option.key]);
              return (
                <div
                  key={option.key}
                  role="button"
                  tabIndex={0}
                  onClick={() => setFeatures((current) => ({ ...current, [option.key]: !checked }))}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setFeatures((current) => ({ ...current, [option.key]: !checked }));
                    }
                  }}
                  className="flex w-full items-start gap-3 rounded-xl border border-border bg-background px-3 py-2.5 text-left transition-colors hover:bg-accent/30"
                >
                  <Checkbox checked={checked} className="pointer-events-none mt-0.5 shrink-0" />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-foreground">{option.name}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">{option.description}</span>
                  </span>
                </div>
              );
            })}
            {featureOptions.length === 0 && (
              <p className="rounded-xl border border-border bg-background px-3 py-4 text-sm text-muted-foreground">
                暂无可配置的 bootstrap feature。
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-4">
        <Button variant="outline" size="sm" disabled={saving} onClick={() => void handleDeleteOrReset()}>
          {item.builtin ? <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> : <Trash2 className="mr-1.5 h-3.5 w-3.5" />}
          {item.builtin ? "重置" : "删除"}
        </Button>
        <Button size="sm" disabled={saving || !dirty || !name.trim()} onClick={() => void handleSave()}>
          <Save className="mr-1.5 h-3.5 w-3.5" />
          保存
        </Button>
      </div>
    </section>
  );
}
