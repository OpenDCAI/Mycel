/**
 * Auth store — JWT token, member identity, login/register/logout.
 * Persisted to localStorage via Zustand persist middleware.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthMember {
  id: string;
  name: string;
  type: string;
}

interface AuthState {
  token: string | null;
  member: AuthMember | null;
  agent: AuthMember | null;
  defaultConversationId: string | null;

  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

async function authCall(endpoint: string, username: string, password: string) {
  const res = await fetch(`/api/auth/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || res.statusText);
  }
  return res.json();
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      member: null,
      agent: null,
      defaultConversationId: null,

      login: async (username, password) => {
        const data = await authCall("login", username, password);
        set({
          token: data.token,
          member: data.member,
          agent: data.agent,
          defaultConversationId: data.conversation_id,
        });
      },

      register: async (username, password) => {
        const data = await authCall("register", username, password);
        set({
          token: data.token,
          member: data.member,
          agent: data.agent,
          defaultConversationId: data.conversation_id,
        });
      },

      logout: () => {
        set({ token: null, member: null, agent: null, defaultConversationId: null });
      },
    }),
    { name: "leon-auth" },
  ),
);

/**
 * Fetch with Bearer token. On 401, clears auth.
 */
export async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, { ...init, headers });
  if (res.status === 401) {
    useAuthStore.getState().logout();
  }
  return res;
}

export async function authRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await authFetch(url, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
