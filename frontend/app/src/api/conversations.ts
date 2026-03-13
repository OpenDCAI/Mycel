import { authRequest } from "../store/auth-store";

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

export interface ConversationSummary {
  id: string;
  agent_member_id: string;
  agent_name: string;
  title: string;
  status: string;
  created_at: number;
  members: string[];
}

export async function createConversation(
  agentMemberId: string,
  title?: string,
): Promise<ConversationSummary> {
  return authRequest<ConversationSummary>("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ agent_member_id: agentMemberId, title }),
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
