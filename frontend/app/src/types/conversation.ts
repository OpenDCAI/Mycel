export interface ConversationItem {
  /** Canonical runtime target for both visit chats and hire threads. */
  id: string;
  type: "hire" | "visit";
  title: string;
  avatar_url: string | null;
  updated_at: string | null;
  unread_count: number;
  running: boolean;
}
