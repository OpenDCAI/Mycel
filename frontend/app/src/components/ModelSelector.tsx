import { Check, ChevronDown, Cpu, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

interface ModelOption {
  id: string;
  name: string;
  description: string;
  provider?: string;
}

const VIRTUAL_MODELS: ModelOption[] = [
  { id: "leon:mini", name: "Mini", description: "快速响应，简单任务" },
  { id: "leon:medium", name: "Medium", description: "平衡性能，日常任务" },
  { id: "leon:large", name: "Large", description: "复杂推理，困难任务" },
  { id: "leon:max", name: "Max", description: "极限性能，最难任务" },
];

interface ModelSelectorProps {
  currentModel: string;
  threadId: string | null;
  onModelChange?: (model: string) => void;
}

export default function ModelSelector({
  currentModel,
  threadId,
  onModelChange,
}: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCustomModels, setShowCustomModels] = useState(
    () => !VIRTUAL_MODELS.some((m) => m.id === currentModel) && !!currentModel
  );
  const [enabledModels, setEnabledModels] = useState<string[]>([]);

  // Fetch enabled models when dropdown opens
  useEffect(() => {
    if (!isOpen) return;
    fetch("/api/settings")
      .then((r) => r.json())
      .then((d) => setEnabledModels(d.enabled_models || []))
      .catch(() => {});
  }, [isOpen]);

  async function handleModelSelect(model: string) {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/settings/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model, thread_id: threadId }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to update model");
      }

      const result = await response.json();
      onModelChange?.(result.model || model);
      setIsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update model");
    } finally {
      setLoading(false);
    }
  }

  const currentModelDisplay = VIRTUAL_MODELS.find((m) => m.id === currentModel)?.name || currentModel;

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <button
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-sm text-foreground/70 hover:bg-accent hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Cpu className="w-3.5 h-3.5" />
          <span className="max-w-[120px] truncate">{currentModelDisplay}</span>
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" />
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-48 p-1">
        {VIRTUAL_MODELS.map((model) => (
          <button
            key={model.id}
            onClick={() => handleModelSelect(model.id)}
            disabled={loading}
            className="w-full flex items-center justify-between py-1.5 px-3 hover:bg-accent rounded-md disabled:opacity-50 text-left"
          >
            <span className="text-sm">{model.name}</span>
            {currentModel === model.id && (
              <Check className="w-3.5 h-3.5 text-primary flex-shrink-0 ml-2" />
            )}
          </button>
        ))}

        <div className="border-t border-border my-1" />
        <div className="flex items-center justify-between px-3 py-1.5">
          <span className="text-xs text-muted-foreground">Custom</span>
          <button
            onClick={() => setShowCustomModels(!showCustomModels)}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${showCustomModels ? "bg-primary" : "bg-muted"}`}
          >
            <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${showCustomModels ? "translate-x-4" : "translate-x-0.5"}`} />
          </button>
        </div>
        {showCustomModels && enabledModels.map((id) => (
          <button
            key={id}
            onClick={() => handleModelSelect(id)}
            disabled={loading}
            className="w-full flex items-center justify-between py-1.5 px-3 hover:bg-accent rounded-md disabled:opacity-50 text-left"
          >
            <span className="text-xs truncate">{id}</span>
            {currentModel === id && (
              <Check className="w-4 h-4 text-primary flex-shrink-0 ml-2" />
            )}
          </button>
        ))}

        {error && (
          <div className="mx-2 mt-1 px-3 py-2 bg-destructive/10 border border-destructive/20 rounded-lg">
            <p className="text-xs text-destructive">{error}</p>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
