import { beforeEach, describe, expect, it, vi } from "vitest";

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
});
