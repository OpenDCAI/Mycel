import {
  FolderOpen,
  Terminal,
  Activity,
  Camera,
  Globe,
  Cpu,
  Webhook,
  HardDrive,
} from "lucide-react";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import type { ProviderCapabilities } from "./types";
import { CAPABILITY_KEYS, CAPABILITY_LABELS } from "./capabilities";

export const CAPABILITY_ICON_MAP: Record<string, React.ElementType> = {
  filesystem: FolderOpen,
  terminal: Terminal,
  metrics: Activity,
  screenshot: Camera,
  web: Globe,
  process: Cpu,
  hooks: Webhook,
  mount: HardDrive,
};

/** Compact icon strip for ProviderCard — shows lit/dim icons inline */
export function CapabilityStrip({ capabilities }: { capabilities: ProviderCapabilities }) {
  const enabledCount = CAPABILITY_KEYS.filter((k) => capabilities[k]).length;

  return (
    <div className="flex items-center gap-1">
      {CAPABILITY_KEYS.map((key) => {
        const Icon = CAPABILITY_ICON_MAP[key];
        const has = capabilities[key];
        return (
          <Tooltip key={key}>
            <TooltipTrigger asChild>
              <div
                className={[
                  "w-5 h-5 rounded flex items-center justify-center transition-colors duration-fast",
                  has ? "bg-foreground/8 text-foreground" : "text-border",
                ].join(" ")}
              >
                <Icon className="w-3 h-3" />
              </div>
            </TooltipTrigger>
            <TooltipContent>{CAPABILITY_LABELS[key]}</TooltipContent>
          </Tooltip>
        );
      })}
      <span className="text-2xs text-muted-foreground ml-1 font-mono">{enabledCount}/{CAPABILITY_KEYS.length}</span>
    </div>
  );
}

/** Detailed capability tiles for ProviderDetail */
export function CapabilityGrid({ capabilities }: { capabilities: ProviderCapabilities }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {CAPABILITY_KEYS.map((key) => {
        const Icon = CAPABILITY_ICON_MAP[key];
        const has = capabilities[key];
        return (
          <div
            key={key}
            className={[
              "flex items-center gap-2 px-3 py-2 rounded-lg border transition-all duration-fast",
              has
                ? "border-foreground/15 bg-foreground/[0.04] shadow-sm"
                : "border-transparent bg-muted/30 opacity-40",
            ].join(" ")}
          >
            <div
              className={[
                "w-6 h-6 rounded-md flex items-center justify-center shrink-0",
                has ? "bg-foreground/10 text-foreground" : "bg-muted text-muted-foreground",
              ].join(" ")}
            >
              <Icon className="w-3.5 h-3.5" />
            </div>
            <span className={`text-xs ${has ? "text-foreground font-medium" : "text-muted-foreground"}`}>
              {CAPABILITY_LABELS[key]}
            </span>
          </div>
        );
      })}
    </div>
  );
}
