import { useEffect, useMemo, useState } from "react";
import { RotateCcw, Save, Trash2, X } from "lucide-react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAppStore } from "@/store/app-store";
import type { ResourceItem } from "@/store/types";
import type { RecipeFeatureOption } from "@/api/types";

interface Props {
  item: ResourceItem | null;
  providerTypeOptions: Array<{ value: string; label: string }>;
  featureOptions: RecipeFeatureOption[];
  onClose: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  onCreated?: (item: ResourceItem) => void;
  onDeleted?: () => void;
}

function buildDefaultFeatureState(featureOptions: RecipeFeatureOption[]): Record<string, boolean> {
  return Object.fromEntries(featureOptions.map((option) => [option.key, false]));
}

export default function RecipeEditor({
  item,
  providerTypeOptions,
  featureOptions,
  onClose,
  onDirtyChange,
  onCreated,
  onDeleted,
}: Props) {
  const updateResource = useAppStore((s) => s.updateResource);
  const addResource = useAppStore((s) => s.addResource);
  const deleteResource = useAppStore((s) => s.deleteResource);
  const isCreate = item == null;

  const [name, setName] = useState(item?.name ?? "");
  const [desc, setDesc] = useState(item?.desc ?? "");
  const [providerType, setProviderType] = useState(item?.provider_type ?? providerTypeOptions[0]?.value ?? "local");
  const [features, setFeatures] = useState<Record<string, boolean>>(
    item?.features ?? buildDefaultFeatureState(featureOptions),
  );
  const [saving, setSaving] = useState(false);
  const [destructiveOpen, setDestructiveOpen] = useState(false);

  useEffect(() => {
    setName(item?.name ?? "");
    setDesc(item?.desc ?? "");
    setProviderType(item?.provider_type ?? providerTypeOptions[0]?.value ?? "local");
    setFeatures(item?.features ?? buildDefaultFeatureState(featureOptions));
  }, [featureOptions, item, providerTypeOptions]);

  const dirty = useMemo(() => {
    if (isCreate) {
      if (name.trim().length > 0) return true;
      if (desc.trim().length > 0) return true;
      if (providerType !== (providerTypeOptions[0]?.value ?? "local")) return true;
      return Object.values(features).some(Boolean);
    }
    if (!item) return false;
    if (name !== item.name || desc !== item.desc) return true;
    const base = item.features ?? {};
    const keys = new Set([...Object.keys(base), ...Object.keys(features)]);
    return [...keys].some((key) => Boolean(base[key]) !== Boolean(features[key]));
  }, [desc, features, isCreate, item, name, providerType, providerTypeOptions]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => {
      onDirtyChange?.(false);
    };
  }, [dirty, onDirtyChange]);

  async function handleSave() {
    setSaving(true);
    try {
      if (isCreate) {
        const created = await addResource("recipe", name.trim(), desc.trim(), {
          provider_type: providerType,
          features,
        });
        toast.success("Recipe 已创建");
        onCreated?.(created);
      } else if (item) {
        await updateResource("recipe", item.id, {
          name,
          desc,
          features,
        });
        toast.success("Recipe 已保存");
      }
    } catch (error) {
      toast.error(`${isCreate ? "创建" : "保存"}失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleDestructiveAction() {
    setSaving(true);
    try {
      if (!item) return;
      await deleteResource("recipe", item.id);
      toast.success(item.builtin ? "已重置为默认配置" : "Recipe 已删除");
      setDestructiveOpen(false);
      onDeleted?.();
      onClose();
    } catch (error) {
      toast.error(`${item?.builtin ? "重置" : "删除"}失败: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(false);
    }
  }

  const saveDisabled = saving || (!isCreate && !dirty) || (isCreate && name.trim().length === 0);
  const visibleFeatureOptions = (item?.feature_options?.length ? item.feature_options : featureOptions);
  const destructiveTitle = item?.builtin ? "重置 recipe" : "删除 recipe";
  const destructiveDescription = item?.builtin
    ? "这会丢掉你对默认 recipe 的自定义修改，并恢复到系统默认值。"
    : "这会永久删除这个自定义 recipe。";

  return (
    <div className="w-[420px] shrink-0 border-l border-border bg-card flex flex-col overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-4 py-4 border-b border-border shrink-0">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground truncate">{isCreate ? "新建 Recipe" : item?.name}</h3>
          <div className="mt-1 text-xs text-muted-foreground">
            {isCreate ? "创建一个按 provider type 复用的 sandbox 模板" : item?.provider_type}
          </div>
        </div>
        <button onClick={onClose} className="p-1 rounded-md hover:bg-muted transition-colors shrink-0">
          <X className="w-4 h-4 text-muted-foreground" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Name</div>
          <Input value={name} onChange={(e) => setName(e.target.value)} className="h-9 text-sm" />
        </div>

        {isCreate && (
          <div className="space-y-2">
            <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Provider Type</div>
            <Select value={providerType} onValueChange={setProviderType}>
              <SelectTrigger className="h-9 text-sm">
                <SelectValue placeholder="Choose a provider type" />
              </SelectTrigger>
              <SelectContent>
                {providerTypeOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Description</div>
          <Input value={desc} onChange={(e) => setDesc(e.target.value)} className="h-9 text-sm" />
        </div>

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Features</div>
          <div className="space-y-1.5">
            {visibleFeatureOptions.map((option) => {
              const checked = Boolean(features[option.key]);
              return (
                <div
                  key={option.key}
                  onClick={() => setFeatures((current) => ({ ...current, [option.key]: !checked }))}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setFeatures((current) => ({ ...current, [option.key]: !checked }));
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  className="flex w-full items-start gap-3 rounded-xl border border-border bg-background px-3 py-2.5 text-left transition-colors hover:bg-accent/30"
                >
                  <Checkbox checked={checked} className="pointer-events-none mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground">{option.name}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{option.description}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-3 shrink-0">
        {isCreate ? <div /> : (
          <Button size="sm" variant="outline" className="h-8" disabled={saving} onClick={() => setDestructiveOpen(true)}>
            {item?.builtin ? <RotateCcw className="h-3.5 w-3.5 mr-1" /> : <Trash2 className="h-3.5 w-3.5 mr-1" />}
            {item?.builtin ? "重置" : "删除"}
          </Button>
        )}
        <Button
          size="sm"
          className={dirty ? "h-8 ring-2 ring-primary/20" : "h-8"}
          disabled={saveDisabled}
          onClick={() => void handleSave()}
        >
          <Save className="h-3.5 w-3.5 mr-1" /> {isCreate ? "创建" : "保存"}
        </Button>
      </div>

      <AlertDialog open={destructiveOpen} onOpenChange={setDestructiveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{destructiveTitle}</AlertDialogTitle>
            <AlertDialogDescription>{destructiveDescription}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleDestructiveAction()}>
              {item?.builtin ? "确认重置" : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
