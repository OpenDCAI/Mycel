const AVATAR_COLORS = [
  "bg-primary text-primary-foreground",
  "bg-success text-success-foreground",
  "bg-warning text-warning-foreground",
  "bg-destructive text-destructive-foreground",
  "bg-chart-1 text-chart-1-foreground",
  "bg-accent text-accent-foreground",
];

export function getMemberColor(memberId: string): string {
  if (!memberId) return AVATAR_COLORS[0];
  const hash = memberId.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

export function getMemberInitials(name: string): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
