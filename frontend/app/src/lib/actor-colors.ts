/**
 * @@@actor-colors - single source of truth for actor type colors.
 * Used by ActorAvatar (DOM/Tailwind) and NetworkPage (Canvas/hex).
 */

// Type → color mapping. Each entry has both Canvas hex and Tailwind classes.
const TYPE_COLORS: Record<string, { hex: string; tw: string }> = {
  human:          { hex: "#60a5fa", tw: "bg-blue-100 text-blue-700" },
  mycel_agent:    { hex: "#4ade80", tw: "bg-green-100 text-green-700" },
  openclaw_agent: { hex: "#fb923c", tw: "bg-orange-100 text-orange-700" },
};

const DEFAULT_TYPE_COLOR = { hex: "#a78bfa", tw: "bg-purple-100 text-purple-700" };

/** Resolve color by actor type. Returns both hex (Canvas) and tw (DOM) variants. */
export function colorForType(type?: string): { hex: string; tw: string } {
  return (type && TYPE_COLORS[type]) || DEFAULT_TYPE_COLOR;
}

// ID-hash colors for actors without a known type.
const ID_HASH_COLORS = [
  "bg-blue-100 text-blue-700",
  "bg-green-100 text-green-700",
  "bg-purple-100 text-purple-700",
  "bg-orange-100 text-orange-700",
  "bg-pink-100 text-pink-700",
  "bg-teal-100 text-teal-700",
];

/** Deterministic color from actor ID hash. Used when type is unavailable. */
export function colorForId(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0;
  return ID_HASH_COLORS[Math.abs(hash) % ID_HASH_COLORS.length];
}

export function getInitials(name: string): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}
