import React from "react";

export const API_BASE = "/api/monitor";
export const MONITOR_TOKEN_KEY = "leon-monitor-token";

export type MonitorFetchError = Error & {
  status?: number;
  payload?: unknown;
};

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;

  const explicit = window.localStorage.getItem(MONITOR_TOKEN_KEY)?.trim();
  if (explicit) return explicit;

  const rawAuth = window.localStorage.getItem("leon-auth");
  if (!rawAuth) return null;

  try {
    const parsed = JSON.parse(rawAuth) as { state?: { token?: unknown } };
    return typeof parsed.state?.token === "string" && parsed.state.token.trim()
      ? parsed.state.token.trim()
      : null;
  } catch {
    return null;
  }
}

export async function fetchAPI<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  const token = readStoredToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const text = await res.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!res.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail?: unknown }).detail ?? `Request failed (${res.status})`)
        : text || `Request failed (${res.status})`;
    const error = new Error(detail) as MonitorFetchError;
    error.status = res.status;
    error.payload = payload;
    throw error;
  }

  return payload as T;
}

export function useMonitorData<T>(path: string) {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<MonitorFetchError | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);

    fetchAPI<T>(path)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? (err as MonitorFetchError) : new Error(String(err)));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [path]);

  return { data, error };
}

export function readMonitorToken(): string | null {
  return readStoredToken();
}

export async function postMonitorData<T>(path: string, body?: unknown): Promise<T> {
  return fetchAPI<T>(path, {
    method: "POST",
    body: body == null ? undefined : JSON.stringify(body),
  });
}
