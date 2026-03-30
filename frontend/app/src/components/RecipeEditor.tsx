import { useEffect, useMemo, useState } from "react";
import { RotateCcw, Save, X } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/store/app-store";
import type { ResourceItem } from "@/store/types";

interface Props {
  item: ResourceItem;
  onClose: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}

export default function RecipeEditor({ item, onClose, onDirtyChange }: Props) {
  const updateResource = useAppStore((s) => s.updateResource);
  const deleteResource = useAppStore((s) => s.deleteResource);

  const [name, setName] = useState(item.name);
  const [desc, setDesc] = useState(item.desc);
  const [features, setFeatures] = useState<Record<string, boolean>>(item.features ?? {});
  const [saving, setSaving] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);

  useEffect(() => {
    setName(item.name);
    setDesc(item.desc);
    setFeatures(item.features ?? {});
  }, [item]);

  const featureOptions = item.feature_options ?? [];
  const dirty = useMemo(() => {
    if (name !== item.name || desc !== item.desc) return true;
    const base = item.features ?? {};
    const keys = new Set([...Object.keys(base), ...Object.keys(features)]);
    return [...keys].some((key) => Boolean(base[key]) !== Boolean(features[key]));
  }, [desc, features, item.desc, item.features, item.name, name]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => {
      onDirtyChange?.(false);
    };
  }, [dirty, onDirtyChange]);

  async function handleSave() {
    setSaving(true);
    try {
      await updateResource("recipe", item.id, {
        name,
        desc,
        features,
      });
      toast.success("Recipe 已保存");
    } catch (error) {
      toast.error(`保存失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    setSaving(true);
    try {
      await deleteResource("recipe", item.id);
      toast.success("已重置为默认配置");
      setResetOpen(false);
      onClose();
    } catch (error) {
      toast.error(`重置失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="w-[420px] shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">
      <div className="h-12 flex items-center justify-between px-4 border-b border-border shrink-0">
        <h3 className="text-sm font-semibold text-foreground truncate">{item.name}</h3>
        <div className="flex items-center gap-1.5 shrink-0">
          <Button size="sm" variant="outline" className="h-7" disabled={saving} onClick={() => setResetOpen(true)}>
            <RotateCcw className="h-3.5 w-3.5 mr-1" /> 重置
          </Button>
          <Button
            size="sm"
            className={dirty ? "h-7 ring-2 ring-primary/20" : "h-7"}
            disabled={!dirty || saving}
            onClick={() => void handleSave()}
          >
            <Save className="h-3.5 w-3.5 mr-1" /> 保存
          </Button>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Provider</div>
          <div className="text-sm text-foreground">{item.provider_name}</div>
        </div>

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Name</div>
          <Input value={name} onChange={(e) => setName(e.target.value)} className="h-9 text-sm" />
        </div>

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Description</div>
          <Input value={desc} onChange={(e) => setDesc(e.target.value)} className="h-9 text-sm" />
        </div>

        <div className="space-y-3">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Temporary Features</div>
          <div className="grid gap-2">
            {featureOptions.map((option) => {
              const checked = Boolean(features[option.key]);
              return (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setFeatures((current) => ({ ...current, [option.key]: !checked }))}
                  className="w-full rounded-2xl border border-border bg-background px-4 py-3 text-left transition-colors hover:bg-accent/30"
                >
                  <div className="flex items-start gap-3">
                    <Checkbox checked={checked} className="pointer-events-none mt-0.5" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-foreground">{option.name}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{option.description}</div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <AlertDialog open={resetOpen} onOpenChange={setResetOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>重置 recipe</AlertDialogTitle>
            <AlertDialogDescription>
              这会丢掉你对默认 recipe 的自定义修改，并恢复到系统默认值。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleReset()}>确认重置</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
