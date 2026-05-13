// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchDefaultModel } from "../api/settings";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("../store/auth-store", () => ({
  authFetch,
  useAuthStore: () => null,
}));

describe("fetchDefaultModel", () => {
  beforeEach(() => {
    authFetch.mockReset();
  });

  it("returns the backend configured default model", async () => {
    authFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ default_model: "leon:medium" }),
    });

    await expect(fetchDefaultModel()).resolves.toBe("leon:medium");
  });

  it("fails when the settings API is unavailable", async () => {
    authFetch.mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => "down",
    });

    await expect(fetchDefaultModel()).rejects.toThrow("Settings API 503: down");
  });

  it("fails when the settings payload does not include default_model", async () => {
    authFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ default_model: "" }),
    });

    await expect(fetchDefaultModel()).rejects.toThrow("Settings payload missing default_model");
  });
});
