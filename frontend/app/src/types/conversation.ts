export interface ConversationItem {
  id: string;
  type: "hire" | "visit";
  title: string;
  member_id: string | null;
  avatar_url: string | null;
  updated_at: string | null;
  unread_count: number;
  running: boolean;
}
