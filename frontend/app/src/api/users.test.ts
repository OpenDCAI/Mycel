// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("@/store/auth-store", () => ({
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

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe("fetchUserChatCandidates", () => {
  it("dedupes concurrent reads against the same in-flight request", async () => {
    const pending = deferred<Response>();
    authFetch.mockReturnValue(pending.promise);

    const { fetchUserChatCandidates } = await import("./users");

    const first = fetchUserChatCandidates();
    const second = fetchUserChatCandidates();

    expect(authFetch).toHaveBeenCalledTimes(1);

    pending.resolve(okJson([
      {
        user_id: "human-2",
        name: "Ada",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "visit",
        can_chat: true,
      },
    ]));

    await expect(first).resolves.toEqual([
      {
        user_id: "human-2",
        name: "Ada",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "visit",
        can_chat: true,
        default_thread_id: null,
      },
    ]);
    await expect(second).resolves.toEqual([
      {
        user_id: "human-2",
        name: "Ada",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "visit",
        can_chat: true,
        default_thread_id: null,
      },
    ]);
  });

  it("does not keep a stale cache after the in-flight request settles", async () => {
    authFetch
      .mockResolvedValueOnce(okJson([
        {
          user_id: "human-2",
          name: "Ada",
          type: "human",
          avatar_url: null,
          owner_name: null,
          is_owned: false,
          relationship_state: "visit",
          can_chat: true,
        },
      ]))
      .mockResolvedValueOnce(okJson([
        {
          user_id: "human-3",
          name: "Grace",
          type: "human",
          avatar_url: null,
          owner_name: null,
          is_owned: false,
          relationship_state: "visit",
          can_chat: true,
        },
      ]));

    const { fetchUserChatCandidates } = await import("./users");

    await expect(fetchUserChatCandidates()).resolves.toEqual([
      {
        user_id: "human-2",
        name: "Ada",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "visit",
        can_chat: true,
        default_thread_id: null,
      },
    ]);
    await expect(fetchUserChatCandidates()).resolves.toEqual([
      {
        user_id: "human-3",
        name: "Grace",
        type: "human",
        avatar_url: null,
        owner_name: null,
        is_owned: false,
        relationship_state: "visit",
        can_chat: true,
        default_thread_id: null,
      },
    ]);

    expect(authFetch).toHaveBeenCalledTimes(2);
  });
});
