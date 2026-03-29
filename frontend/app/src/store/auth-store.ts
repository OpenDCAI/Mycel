/**
 * Auth store — JWT token, user identity, login/register/logout.
 * Persisted to localStorage via Zustand persist middleware.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthIdentity {
  id: string;
  name: string;
  type: string;
  avatar?: string | null;
}

interface AuthState {
  token: string | null;
  user: AuthIdentity | null;
  agent: AuthIdentity | null;
  entityId: string | null;

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
    // Parse FastAPI {"detail": "..."} error format
    try {
      const parsed = JSON.parse(body);
      throw new Error(parsed.detail || body);
    } catch (e) {
      if (e instanceof Error && e.message !== body) throw e;
      throw new Error(body || res.statusText);
    }
  }
  return res.json();
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      agent: null,
      entityId: null,

      login: async (username, password) => {
        const data = await authCall("login", username, password);
        set({
          token: data.token,
          user: data.user,
          agent: data.agent,
          entityId: data.entity_id ?? null,
        });
        // Full reload so all components initialize from fresh auth state
        window.location.href = "/threads";
      },

      register: async (username, password) => {
        const data = await authCall("register", username, password);
        set({
          token: data.token,
          user: data.user,
          agent: data.agent,
          entityId: data.entity_id ?? null,
        });
        // Full reload so all components initialize from fresh auth state
        window.location.href = "/threads";
      },

      logout: () => {
        set({ token: null, user: null, agent: null, entityId: null });
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
  const isFormData = init?.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
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
