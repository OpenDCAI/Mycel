import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StreamEvent } from "./types";

const authFetch = vi.fn();

vi.mock("../store/auth-store", () => ({
  authFetch,
}));

function okJson(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

describe("streaming api contract", () => {
  let api: typeof import("./streaming");

  beforeEach(async () => {
    authFetch.mockReset();
    vi.resetModules();
    api = await import("./streaming");
  });

  it("cancelRun fails loudly when backend reports no active run", async () => {
    authFetch.mockResolvedValue(okJson({ ok: false, message: "No active run found" }));

    await expect(api.cancelRun("thread-1")).rejects.toThrow("No active run found");
  });

  it("postRun reports startup cancellation as a cancelled run", async () => {
    authFetch.mockResolvedValue(okJson({ status: "cancelled", routing: "cancelled", thread_id: "thread-1" }));

    await expect(api.postRun("thread-1", "hello")).rejects.toThrow("Run cancelled");
  });

  it("streams thread events through authenticated fetch without leaking token in the URL", async () => {
    const ac = new AbortController();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: status\ndata: {"_seq":8}\n\n'));
        controller.close();
      },
    });
    authFetch.mockResolvedValue(new Response(body));
    const events: StreamEvent[] = [];

    await api.streamThreadEvents("thread-1", (event) => {
      events.push(event);
      ac.abort();
    }, ac.signal, 7);

    expect(authFetch).toHaveBeenCalledWith("/api/threads/thread-1/events?after=7", { signal: ac.signal });
    expect(events).toEqual([{ type: "status", data: { _seq: 8 } }]);
  });
});
