import { beforeEach, describe, expect, it, vi } from "vitest";

const authFetch = vi.fn();

vi.mock("../store/auth-store", () => ({
  authFetch,
}));

function eventStream(lines: string[]): Response {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(lines.join("\n")));
      controller.close();
    },
  });
  return new Response(body);
}

describe("chat event stream", () => {
  let api: typeof import("./chat-events");

  beforeEach(async () => {
    authFetch.mockReset();
    vi.resetModules();
    api = await import("./chat-events");
  });

  it("streams chat events through authenticated fetch without putting token in the URL", async () => {
    authFetch.mockResolvedValue(
      eventStream([
        "event: message",
        'data: {"id":"msg-1","content":"hello"}',
        "",
        "event: typing_start",
        'data: {"user_id":"agent-1"}',
        "",
      ]),
    );
    const ac = new AbortController();
    const seen: Array<{ type: string; data: unknown }> = [];

    await api.streamChatEvents("chat-1", (event) => seen.push(event), ac.signal);

    expect(authFetch).toHaveBeenCalledWith("/api/chats/chat-1/events", {
      headers: { Accept: "text/event-stream" },
      signal: ac.signal,
    });
    expect(seen).toEqual([
      { type: "message", data: { id: "msg-1", content: "hello" } },
      { type: "typing_start", data: { user_id: "agent-1" } },
    ]);
  });
});
