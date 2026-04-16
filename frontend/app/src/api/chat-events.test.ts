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

  it("parses chat message and typing event data at the API boundary", () => {
    expect(api.parseChatMessageEventData({
      id: "msg-1",
      chat_id: "chat-1",
      sender_id: "agent-1",
      sender_name: "Toad",
      content: "hello",
      mentioned_ids: ["user-1"],
      created_at: 1,
    })).toEqual({
      id: "msg-1",
      chat_id: "chat-1",
      sender_id: "agent-1",
      sender_name: "Toad",
      content: "hello",
      mentioned_ids: ["user-1"],
      created_at: 1,
    });
    expect(api.parseChatTypingUserId({ user_id: "agent-1" })).toBe("agent-1");
    expect(api.parseChatTypingUserId({})).toBeNull();
    expect(() => api.parseChatMessageEventData({ id: "msg-1" })).toThrow("chat_id must be a string");
    expect(() => api.parseChatMessageEventData({
      id: "msg-1",
      chat_id: "chat-1",
      sender_id: "agent-1",
      sender_name: "Toad",
      content: "hello",
      mentioned_ids: ["user-1", 7],
      created_at: 1,
    })).toThrow("mentioned_ids must be a string array");
  });

  it("treats abort-time reader network errors as clean teardown, not a stream failure", async () => {
    const cancel = vi.fn();
    let rejectRead: ((reason?: unknown) => void) | null = null;
    const read = vi.fn(() =>
      new Promise<never>((_, reject) => {
        rejectRead = reject;
      }),
    );
    authFetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read,
          cancel,
        }),
      },
    });

    const ac = new AbortController();
    const stream = api.streamChatEvents("chat-1", () => undefined, ac.signal);
    await Promise.resolve();
    ac.abort();
    rejectRead?.(new TypeError("network error"));

    await expect(stream).resolves.toBeUndefined();
    expect(cancel).toHaveBeenCalled();
  });
});
