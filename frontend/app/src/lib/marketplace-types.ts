export const HUB_AGENT_USER_TYPE = "member";

export function marketplaceTypeLabel(type: string): string {
  if (type === HUB_AGENT_USER_TYPE) return "Agent";
  if (type === "agent") return "Subagent";
  return type;
}
