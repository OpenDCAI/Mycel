import type { StreamEvent, TaskAgentRequest } from "./types";
import { processChunk } from "./sse-processor";

/** Read an SSE response body, dispatch events, return { lastSeq, runEnded }. */
async function consumeSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
  startSeq: number,
): Promise<{ lastSeq: number; runEnded: boolean }> {
  const decoder = new TextDecoder();
  let buffer = "";
  let seq = startSeq;
  let runEnded = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\r?\n\r?\n/);
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const result = processChunk(chunk, onEvent, seq);
      seq = result.seq;
      if (result.runEnded) runEnded = true;
      // Persistent stream — never break on runEnded
    }
  }
  return { lastSeq: seq, runEnded };
}

async function postJSON<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  options?: { model?: string; enable_trajectory?: boolean },
): Promise<{ run_id: string; thread_id: string }> {
  return postJSON(`/api/threads/${encodeURIComponent(threadId)}/runs`, { message, ...options }, signal);
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
      const url = `/api/threads/${encodeURIComponent(threadId)}/events?after=${after}`;
      const res = await fetch(url, { signal });

      if (!res.ok) {
        // 4xx = unrecoverable
        if (res.status >= 400 && res.status < 500) {
          onEvent({ type: "error", data: { error: `SSE connect failed: ${res.status}` } });
          return;
        }
        throw new Error(`SSE ${res.status}`);
      }
      if (!res.body) return;

      attempts = 0;
      const { lastSeq } = await consumeSSEStream(res.body.getReader(), onEvent, after);
      after = lastSeq;

      // Server closed connection (normal disconnect) — reconnect
      if (signal?.aborted) return;
    } catch {
      if (signal?.aborted) return;
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
  const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}/runs/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(`Cancel failed: ${res.statusText}`);
}

/** Start a task agent and subscribe to its event stream. */
export async function runTaskAgent(
  threadId: string,
  taskRequest: TaskAgentRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await postJSON(`/api/threads/${encodeURIComponent(threadId)}/task-agent/runs`, taskRequest, signal);
  await streamThreadEvents(threadId, onEvent, signal);
}
