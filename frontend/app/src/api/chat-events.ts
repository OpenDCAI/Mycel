import { authFetch } from "../store/auth-store";

export interface ChatStreamEvent {
  type: string;
  data: unknown;
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
      const { done, value } = await reader.read();
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
