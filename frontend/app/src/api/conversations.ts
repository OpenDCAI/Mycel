import { authFetch, authRequest } from "../store/auth-store";
import { useAuthStore } from "../store/auth-store";

// @@@member-directory - types + fetch for member discovery (shared with agent logbook)
export interface DirectoryEntry {
  id: string;
  name: string;
  type: string;
  description: string | null;
  owner: { id: string; name: string } | null;
  is_contact: boolean;
}

export interface DirectoryResult {
  contacts: DirectoryEntry[];
  others: DirectoryEntry[];
}

export async function listDirectory(type?: string, search?: string): Promise<DirectoryResult> {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (search) params.set("search", search);
  const qs = params.toString();
  return authRequest<DirectoryResult>(`/api/members/directory${qs ? `?${qs}` : ""}`);
}

/** Canonical member identity — shared across network graph, chat, directory. */
export interface MemberInfo {
  id: string;
  name: string;
  type: string;
  avatar?: string | null;
}

/** @deprecated Use MemberInfo */
export type ConversationMemberDetail = MemberInfo;

export interface ConversationSummary {
  id: string;
  title: string;
  status: string;
  created_at: number;
  members: string[];
  member_details?: MemberInfo[];
  /** Non-null only when the requesting user owns the agent. */
  brain_thread_id?: string | null;
}

export async function createMemberConversation(
  memberId: string,
  title?: string,
): Promise<ConversationSummary> {
  const currentMemberId = useAuthStore.getState().member?.id;
  if (!currentMemberId) throw new Error("Not authenticated");
  return authRequest<ConversationSummary>("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ members: [currentMemberId, memberId], title }),
  });
}

export async function listConversations(): Promise<ConversationSummary[]> {
  return authRequest<ConversationSummary[]>("/api/conversations");
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  sender_id: string;
  content: string;
  created_at: number;
}

export async function listMessages(
  conversationId: string,
  limit = 50,
): Promise<ConversationMessage[]> {
  return authRequest<ConversationMessage[]>(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages?limit=${limit}`,
  );
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await authRequest(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
  });
}

export async function sendConversationMessage(
  conversationId: string,
  content: string,
): Promise<Record<string, unknown>> {
  return authRequest(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

/** Upload avatar for a member. Returns true on success. */
export async function uploadMemberAvatar(memberId: string, file: File): Promise<boolean> {
  const form = new FormData();
  form.append("file", file);
  const res = await authFetch(`/api/members/${memberId}/avatar`, {
    method: "PUT",
    body: form,
  });
  return res.ok;
}
