import { authFetch } from "@/store/auth-store";

export type EntityItem = {
  user_id: string;
  name: string;
  type: string;
  avatar_url?: string | null;
  owner_name?: string | null;
  default_thread_id?: string | null;
  is_default_thread?: boolean | null;
  branch_index?: number | null;
  is_owned: boolean;
  relationship_state: string;
  can_chat: boolean;
};

export function parseEntities(value: unknown): EntityItem[] {
  if (!Array.isArray(value)) throw new Error("Malformed entity list");
  return value.map((item) => {
    if (!item || typeof item !== "object") throw new Error("Malformed entity list");
    const row = item as Record<string, unknown>;
    if (
      typeof row.user_id !== "string"
      || typeof row.name !== "string"
      || typeof row.type !== "string"
      || typeof row.is_owned !== "boolean"
      || typeof row.relationship_state !== "string"
      || typeof row.can_chat !== "boolean"
    ) {
      throw new Error("Malformed entity list");
    }
    return {
      user_id: row.user_id,
      name: row.name,
      type: row.type,
      avatar_url: typeof row.avatar_url === "string" ? row.avatar_url : null,
      owner_name: typeof row.owner_name === "string" ? row.owner_name : null,
      default_thread_id: typeof row.default_thread_id === "string" ? row.default_thread_id : null,
      is_default_thread: typeof row.is_default_thread === "boolean" ? row.is_default_thread : null,
      branch_index: typeof row.branch_index === "number" ? row.branch_index : null,
      is_owned: row.is_owned,
      relationship_state: row.relationship_state,
      can_chat: row.can_chat,
    };
  });
}

export async function fetchEntities(): Promise<EntityItem[]> {
  const response = await authFetch("/api/entities");
  if (!response.ok) throw new Error(`Entities API ${response.status}: ${await response.text()}`);
  return parseEntities(await response.json());
}
