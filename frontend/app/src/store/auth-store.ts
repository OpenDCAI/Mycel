/**
 * Auth store — JWT token, user identity, login/register/logout.
 * Persisted to localStorage via Zustand persist middleware.
 *
 * Set VITE_DEV_SKIP_AUTH=true in .env.development to bypass login during dev.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const DEV_SKIP_AUTH = import.meta.env.VITE_DEV_SKIP_AUTH === "true";

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

  login: (identifier: string, password: string) => Promise<void>;
  sendOtp: (email: string, password: string, inviteCode: string) => Promise<void>;
  verifyOtp: (email: string, token: string) => Promise<{ tempToken: string }>;
  completeRegister: (tempToken: string, inviteCode: string) => Promise<{ userId: string; defaultName: string }>;
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
      else if (Array.isArray(detail)) message = detail.map((d: { msg: string }) => d.msg).join("; ");
      else if (detail != null) message = JSON.stringify(detail);
    } catch { /* not JSON, use raw text */ }
    throw new Error(message);
  }
  return res.json();
}

const DEV_MOCK_USER: AuthIdentity = { id: "dev-user", name: "Dev", type: "human" };

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: DEV_SKIP_AUTH ? "dev-skip-auth" : null,
      user: DEV_SKIP_AUTH ? DEV_MOCK_USER : null,
      agent: null,
      entityId: DEV_SKIP_AUTH ? "dev-user" : null,

      login: async (identifier, password) => {
        const data = await apiPost("login", { identifier, password });
        set({
          token: data.token,
          user: data.user,
          agent: data.agent,
          entityId: data.entity_id ?? null,
        });
        window.location.href = "/threads";
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
          entityId: data.entity_id ?? null,
        });
        return { userId: data.user.id, defaultName: data.user.name };
      },

      logout: () => {
        set({ token: null, user: null, agent: null, entityId: null });
      },
    }),
    {
      name: "leon-auth",
      ...(DEV_SKIP_AUTH && {
        // In skip-auth mode, never let persisted null overwrite the mock identity
        merge: (_persisted: unknown, current: AuthState) => current,
      }),
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
  if (res.status === 401 && !DEV_SKIP_AUTH) {
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
