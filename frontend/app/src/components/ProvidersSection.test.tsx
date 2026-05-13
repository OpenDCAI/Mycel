// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProvidersSection from "./ProvidersSection";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("ProvidersSection", () => {
  it("hides BYOK fields while a provider uses platform resources", () => {
    render(
      <ProvidersSection
        providers={{ anthropic: { api_key: null, has_api_key: false, credential_source: "platform", base_url: null } }}
        onUpdate={vi.fn()}
      />,
    );

    expect(screen.queryByText("API 密钥")).toBeNull();
    expect(screen.queryByText("自定义 Base URL")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Anthropic 使用自己的 API Key" }));

    expect(screen.getByText("API 密钥")).toBeTruthy();
    expect(screen.getByText("自定义 Base URL")).toBeTruthy();
  });

  it("keeps BYOK input local until the user explicitly saves", async () => {
    window.history.replaceState({}, "", "/settings");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ success: true }), { status: 200 }));
    const onUpdate = vi.fn();

    render(
      <ProvidersSection
        providers={{ anthropic: { api_key: null, has_api_key: false, credential_source: "platform", base_url: null } }}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Anthropic 使用自己的 API Key" }));
    fireEvent.change(screen.getByPlaceholderText("输入 Anthropic API 密钥"), {
      target: { value: "sk-test" },
    });

    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "保存 Anthropic 设置" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledOnce();
    });
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      provider: "anthropic",
      credential_source: "user",
      api_key: "sk-test",
    });
    expect(onUpdate).toHaveBeenCalledWith("anthropic", expect.objectContaining({
      api_key: null,
      has_api_key: true,
      credential_source: "user",
    }));
  });

  it("submits platform credential source without resending a stored key", async () => {
    window.history.replaceState({}, "", "/settings");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ success: true }), { status: 200 }));

    render(
      <ProvidersSection
        providers={{ anthropic: { api_key: null, has_api_key: true, credential_source: "user", base_url: null } }}
        onUpdate={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Anthropic 使用平台资源" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledOnce();
    });
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      provider: "anthropic",
      credential_source: "platform",
      api_key: null,
    });
  });

  it("does not log a failed provider save once navigation already left /settings", async () => {
    window.history.replaceState({}, "", "/settings");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      window.history.replaceState({}, "", "/chat");
      throw new TypeError("Failed to fetch");
    });

    render(
      <ProvidersSection
        providers={{ anthropic: { api_key: null, base_url: null } }}
        onUpdate={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Anthropic 使用自己的 API Key" }));
    fireEvent.change(screen.getByPlaceholderText("输入 Anthropic API 密钥"), {
      target: { value: "sk-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 Anthropic 设置" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledOnce();
    });

    await waitFor(() => {
      expect(consoleError).not.toHaveBeenCalled();
    });
  });

  it("does not update provider state when persistence fails", async () => {
    window.history.replaceState({}, "", "/settings");
    const onUpdate = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("down", { status: 503 }));

    render(
      <ProvidersSection
        providers={{ anthropic: { api_key: null, base_url: null } }}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Anthropic 使用自己的 API Key" }));
    fireEvent.change(screen.getByPlaceholderText("输入 Anthropic API 密钥"), {
      target: { value: "sk-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 Anthropic 设置" }));

    expect(await screen.findByText("保存失败：API 503: down")).toBeTruthy();
    expect(onUpdate).not.toHaveBeenCalled();
    expect(screen.queryByText("已保存")).toBeNull();
  });
});
