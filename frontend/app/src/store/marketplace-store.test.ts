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
    expect(consoleError).not.toHaveBeenCalled();
  });
});
