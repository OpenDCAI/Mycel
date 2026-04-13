// @@@hub-agent-user-item-type - Hub still names published Agent users "member";
// app UI must keep exposing them as Agent users.
export const HUB_AGENT_USER_ITEM_TYPE = "member";

export function marketplaceTypeLabel(type: string): string {
  if (type === HUB_AGENT_USER_ITEM_TYPE) return "Agent";
  if (type === "agent") return "Subagent";
  return type;
}
