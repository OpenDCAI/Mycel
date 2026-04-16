import { authFetch } from "../store/auth-store";
import { asRecord } from "../lib/records";
import type { ChatMessage } from "./types";

export interface ChatStreamEvent {
  type: string;
  data: unknown;
}

function isAbortTeardownError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof TypeError && error.message === "network error";
}

function requiredString(value: Record<string, unknown>, key: string): string {
  const field = value[key];
  if (typeof field !== "string") {
    throw new Error(`Malformed chat message event: ${key} must be a string`);
  }
  return field;
}

function requiredNumber(value: Record<string, unknown>, key: string): number {
  const field = value[key];
  if (typeof field !== "number") {
    throw new Error(`Malformed chat message event: ${key} must be a number`);
  }
  return field;
}

function requiredStringArray(value: Record<string, unknown>, key: string): string[] {
  const field = value[key];
  if (!Array.isArray(field) || field.some((item) => typeof item !== "string")) {
    throw new Error(`Malformed chat message event: ${key} must be a string array`);
  }
  return field;
}

export function parseChatMessageEventData(data: unknown): ChatMessage {
  const value = asRecord(data);
  if (!value) throw new Error("Malformed chat message event: data must be an object");
  return {
    id: requiredString(value, "id"),
    chat_id: requiredString(value, "chat_id"),
    sender_id: requiredString(value, "sender_id"),
    sender_name: requiredString(value, "sender_name"),
    content: requiredString(value, "content"),
    mentioned_ids: requiredStringArray(value, "mentioned_ids"),
    created_at: requiredNumber(value, "created_at"),
  };
}

export function parseChatTypingUserId(data: unknown): string | null {
  const value = asRecord(data);
  const userId = value?.user_id;
  return typeof userId === "string" && userId ? userId : null;
}

function parseEvent(raw: string): ChatStreamEvent | null {
  if (!raw.trim()) return null;
  let type = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  const dataRaw = dataLines.join("\n");
  if (!dataRaw) return null;
  return { type, data: JSON.parse(dataRaw) };
}

export async function streamChatEvents(
  chatId: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await authFetch(`/api/chats/${encodeURIComponent(chatId)}/events`, {
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!res.ok) throw new Error(`Chat event stream failed: ${res.status}: ${await res.text()}`);
  if (!res.body) throw new Error("Chat event stream response has no body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const onAbort = () => reader.cancel();
  signal?.addEventListener("abort", onAbort, { once: true });

  try {
    while (!signal?.aborted) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (error) {
        if (signal?.aborted && isAbortTeardownError(error)) break;
        throw error;
      }
      const { done, value } = chunk;
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split(/\r?\n\r?\n/);
      buffer = chunks.pop() ?? "";
      for (const chunk of chunks) {
        const event = parseEvent(chunk);
        if (event) onEvent(event);
      }
    }
    const trailing = parseEvent(buffer);
    if (trailing) onEvent(trailing);
  } finally {
    signal?.removeEventListener("abort", onAbort);
  }
}
