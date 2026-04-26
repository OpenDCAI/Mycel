import { HUB_AGENT_USER_ITEM_TYPE } from "@/lib/marketplace-types";

export const typeBadgeColors: Record<string, string> = {
  [HUB_AGENT_USER_ITEM_TYPE]: "bg-info/10 text-info",
  agent: "bg-primary/10 text-primary",
  skill: "bg-warning/10 text-warning",
  env: "bg-success/10 text-success",
};
