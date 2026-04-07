export interface ConversationItem {
  id: string;
  type: "hire" | "visit";
  title: string;
  /** Hire entries keep the template entry id here; the actor thread still lives in `id`. */
  member_id: string | null;
  avatar_url: string | null;
  updated_at: string | null;
  unread_count: number;
  running: boolean;
}
