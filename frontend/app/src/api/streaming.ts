import type { StreamEvent } from "./types";
import { processChunk } from "./sse-processor";
import { authFetch } from "../store/auth-store";

/** Read an SSE response body, dispatch events, return { lastSeq, runEnded }. */
async function consumeSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
  startSeq: number,
  signal?: AbortSignal,
): Promise<{ lastSeq: number; runEnded: boolean }> {
  const decoder = new TextDecoder();
  let buffer = "";
  let seq = startSeq;
  let runEnded = false;

  // When signal aborts, cancel the reader to unblock reader.read()
  const onAbort = () => reader.cancel();
  signal?.addEventListener("abort", onAbort, { once: true });

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split(/\r?\n\r?\n/);
      buffer = chunks.pop() ?? "";

      for (const chunk of chunks) {
        if (signal?.aborted) break;
        const result = processChunk(chunk, onEvent, seq);
        seq = result.seq;
        if (result.runEnded) runEnded = true;
      }
    }
  } finally {
    signal?.removeEventListener("abort", onAbort);
  }
  return { lastSeq: seq, runEnded };
}

async function postJSON<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await authFetch(url, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new Error(`POST ${url} failed ${res.status}: ${await res.text()}`);
  return res.json();
}

/** Start an agent run (fire-and-forget). */
export async function postRun(
  threadId: string,
  message: string,
  signal?: AbortSignal,
  options?: { model?: string; enable_trajectory?: boolean; attachments?: string[] },
): Promise<{ run_id: string; thread_id: string }> {
  const payload = await postJSON<{ run_id?: string; thread_id: string; status?: string }>(
    `/api/threads/${encodeURIComponent(threadId)}/messages`,
    { message, ...options },
    signal,
  );
  if (payload.status === "cancelled") throw new Error("Run cancelled");
  if (!payload.run_id) throw new Error("Run did not start");
  return { run_id: payload.run_id, thread_id: payload.thread_id };
}

/** Persistent SSE connection to a thread's event stream. */
export async function streamThreadEvents(
  threadId: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  startAfter = 0,
): Promise<void> {
  let after = startAfter;
  let attempts = 0;
  const MAX_ATTEMPTS = 10;

  while (!signal?.aborted) {
    try {
      const { useAuthStore } = await import("../store/auth-store");
      const token = useAuthStore.getState().token || "";
      const url = `/api/threads/${encodeURIComponent(threadId)}/events?after=${after}&token=${encodeURIComponent(token)}`;
      console.log(`[SSE-FETCH] fetching ${url.replace(/token=[^&]+/, "token=***")}`);
      const res = await fetch(url, { signal: signal });
      if (signal?.aborted) return;
      console.log(`[SSE-FETCH] response status=${res.status}, ok=${res.ok}`);

      if (!res.ok) {
        if (res.status >= 400 && res.status < 500) {
          onEvent({ type: "error", data: { error: `SSE connect failed: ${res.status}` } });
          return;
        }
        throw new Error(`SSE ${res.status}`);
      }
      if (!res.body) return;

      attempts = 0;
      console.log("[SSE-FETCH] consuming SSE stream...");
      const { lastSeq } = await consumeSSEStream(res.body.getReader(), onEvent, after, signal);
      console.log(`[SSE-FETCH] stream ended, lastSeq=${lastSeq}, reconnecting...`);
      after = lastSeq;

      if (signal?.aborted) return;
    } catch (fetchErr) {
      if (signal?.aborted) return;
      console.log(`[SSE-FETCH] catch: ${fetchErr}`);

      if (++attempts > MAX_ATTEMPTS) {
        onEvent({ type: "error", data: { error: "Max reconnection attempts reached" } });
        return;
      }
      // Exponential backoff with jitter
      const base = Math.min(1000 * 2 ** (attempts - 1), 30000);
      const jitter = base * 0.2 * (Math.random() * 2 - 1);
      await new Promise((r) => setTimeout(r, base + jitter));
    }
  }
}

export async function cancelRun(threadId: string): Promise<void> {
  const res = await authFetch(`/api/threads/${encodeURIComponent(threadId)}/runs/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(`Cancel failed: ${res.statusText}`);
  const payload = await res.json();
  if (payload?.ok === false) throw new Error(payload.message || "Cancel failed");
}
