const AVATAR_COLORS = [
  "bg-primary text-primary-foreground",
  "bg-success text-success-foreground",
  "bg-warning text-warning-foreground",
  "bg-destructive text-destructive-foreground",
  "bg-chart-1 text-chart-1-foreground",
  "bg-accent text-accent-foreground",
];

export function getAgentColor(agentId: string): string {
  if (!agentId) return AVATAR_COLORS[0];
  const hash = agentId.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

export function getAgentInitials(name: string): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
