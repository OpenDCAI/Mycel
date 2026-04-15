// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  vi.resetModules();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
  const { useMarketplaceStore } = await import("./marketplace-store");
  useMarketplaceStore.setState({
    items: [],
    total: 0,
    loading: false,
    error: null,
    filters: { type: null, q: "", sort: "downloads", page: 1 },
    detail: null,
    detailLoading: false,
    lineage: { ancestors: [], children: [] },
    updates: [],
    versionSnapshot: null,
    snapshotLoading: false,
    downloading: false,
  });
});

describe("useMarketplaceStore", () => {
  it("does not emit a state update for a no-op filter change", async () => {
    const { useMarketplaceStore } = await import("./marketplace-store");
    const listener = vi.fn();
    const unsubscribe = useMarketplaceStore.subscribe(listener);

    useMarketplaceStore.getState().setFilter("q", "");

    unsubscribe();
    expect(listener).not.toHaveBeenCalled();
  });

  it("does not log a failed items fetch once navigation already left the marketplace route", async () => {
    window.history.replaceState({}, "", "/marketplace");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    const { useMarketplaceStore } = await import("./marketplace-store");

    await useMarketplaceStore.getState().fetchItems();

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/marketplace/items?");
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("localhost:8090");
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("does not log a failed detail fetch once navigation already left the marketplace detail route", async () => {
    window.history.replaceState({}, "", "/marketplace/item-1");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    const { useMarketplaceStore } = await import("./marketplace-store");

    await useMarketplaceStore.getState().fetchDetail("item-1");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/marketplace/items/item-1");
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("localhost:8090");
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("does not log a failed lineage fetch once navigation already left the marketplace detail route", async () => {
    window.history.replaceState({}, "", "/marketplace/item-1");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    const { useMarketplaceStore } = await import("./marketplace-store");

    await useMarketplaceStore.getState().fetchLineage("item-1");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/marketplace/items/item-1/lineage");
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("localhost:8090");
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("does not log a failed snapshot fetch once navigation already left the marketplace detail route", async () => {
    window.history.replaceState({}, "", "/marketplace/item-1");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    const { useMarketplaceStore } = await import("./marketplace-store");

    await useMarketplaceStore.getState().fetchVersionSnapshot("item-1", "1.0.0");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/marketplace/items/item-1/versions/1.0.0");
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("localhost:8090");
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("does not log a failed update check once navigation already left the marketplace route", async () => {
    window.history.replaceState({}, "", "/marketplace?tab=installed");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    const { useMarketplaceStore } = await import("./marketplace-store");

    await useMarketplaceStore.getState().checkUpdates([
      { marketplace_item_id: "item-1", installed_version: "1.0.0" },
    ]);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("publishes agent users through the semantic backend endpoint without a type field", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    } as Response);

    const { useMarketplaceStore } = await import("./marketplace-store");

    await useMarketplaceStore.getState().publishAgentUserToMarketplace("agent-1", "patch", "notes", ["coding"], "public");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/marketplace/publish-agent-user");
    expect(JSON.parse(String(init?.body))).toEqual({
      user_id: "agent-1",
      bump_type: "patch",
      release_notes: "notes",
      tags: ["coding"],
      visibility: "public",
    });
  });
});
