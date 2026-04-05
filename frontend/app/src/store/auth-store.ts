/**
 * Auth store — JWT token, user identity, login/register/logout.
 * Persisted to localStorage via Zustand persist middleware.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

// Allow overriding the API origin at runtime via window.__MYCEL_CONFIG__.apiBase
// (injected by docker-entrypoint.sh), falling back to the Vite build-time variable.
// Relative URLs are used when neither is set (same-origin / local dev).
const API_BASE = (
  (window as { __MYCEL_CONFIG__?: { apiBase?: string } }).__MYCEL_CONFIG__?.apiBase
  ?? import.meta.env.VITE_API_BASE
  ?? ""
).replace(/\/$/, "");
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
  setupInfo: { userId: string; defaultName: string } | null;

  login: (identifier: string, password: string) => Promise<void>;
  sendOtp: (email: string, password: string, inviteCode: string) => Promise<void>;
  verifyOtp: (email: string, token: string) => Promise<{ tempToken: string }>;
  completeRegister: (tempToken: string, inviteCode: string) => Promise<void>;
  clearSetupInfo: () => void;
  logout: () => void;
}

async function apiPost(endpoint: string, body: Record<string, string>) {
  const res = await fetch(`${API_BASE}/api/auth/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = text || res.statusText;
    try {
      const parsed = JSON.parse(text);
      const detail = parsed.detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail)) message = detail.map((d: { msg: string; loc?: string[] }) => `${d.loc?.at(-1) ?? "?"}: ${d.msg}`).join("; ");
      else if (detail != null) message = JSON.stringify(detail);
    } catch { /* not JSON, use raw text */ }
    throw new Error(message);
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
      setupInfo: null,

      login: async (identifier, password) => {
        const data = await apiPost("login", { identifier, password });
        set({
          token: data.token,
          user: data.user,
          agent: data.agent,
          entityId: data.user?.id ?? null,
        });
      },

      sendOtp: async (email, password, inviteCode) => {
        await apiPost("send-otp", { email, password, invite_code: inviteCode });
      },

      verifyOtp: async (email, token) => {
        const data = await apiPost("verify-otp", { email, token });
        return { tempToken: data.temp_token };
      },

      completeRegister: async (tempToken, inviteCode) => {
        const data = await apiPost("complete-register", {
          temp_token: tempToken,
          invite_code: inviteCode,
        });
        set({
          token: data.token,
          user: data.user,
          agent: data.agent ?? null,
          entityId: data.user?.id ?? null,
          setupInfo: { userId: data.user.id, defaultName: data.user.name },
        });
      },

      clearSetupInfo: () => {
        set({ setupInfo: null });
      },

      logout: () => {
        set({ token: null, user: null, agent: null, entityId: null, setupInfo: null });
      },
    }),
    {
      name: "leon-auth",
    },
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

  // Prepend API_BASE for relative URLs when configured
  const resolvedUrl = API_BASE && url.startsWith("/") ? `${API_BASE}${url}` : url;
  const res = await fetch(resolvedUrl, { ...init, headers });
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
