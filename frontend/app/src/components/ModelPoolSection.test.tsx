// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ModelPoolSection from "./ModelPoolSection";

const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("@/store/auth-store", () => ({
  authFetch,
}));

function response(body: unknown, init: { ok?: boolean; status?: number; text?: string } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
    text: async () => init.text ?? JSON.stringify(body),
  };
}

function renderModelPool(options: {
  onToggle?: (modelId: string, enabled: boolean) => void;
  onAddCustomModel?: (modelId: string, provider: string, basedOn?: string, contextLimit?: number) => Promise<void>;
  onRemoveCustomModel?: (modelId: string) => Promise<void>;
} = {}) {
  return render(
    <ModelPoolSection
      models={[{ id: "custom:model", name: "Custom", custom: true }]}
      enabledModels={["custom:model"]}
      customConfig={{}}
      providers={{ openai: { api_key: null, base_url: null } }}
      onToggle={options.onToggle ?? vi.fn()}
      onAddCustomModel={options.onAddCustomModel ?? vi.fn()}
      onRemoveCustomModel={options.onRemoveCustomModel ?? vi.fn()}
    />,
  );
}

afterEach(() => {
  cleanup();
  authFetch.mockReset();
});

describe("ModelPoolSection", () => {
  it("ignores non-string model test errors", async () => {
    authFetch.mockResolvedValue(response({
      success: false,
      error: { message: "not a string" },
    }));

    renderModelPool();

    fireEvent.click(screen.getByRole("button", { name: "测试" }));

    expect(await screen.findByText("测试失败")).toBeTruthy();
    expect(screen.queryByText("[object Object]")).toBeNull();
  });

  it("does not accept non-boolean model test success values", async () => {
    authFetch.mockResolvedValue(response({ success: "yes" }));

    renderModelPool();

    fireEvent.click(screen.getByRole("button", { name: "测试" }));

    await waitFor(() => {
      expect(screen.getByText("测试失败")).toBeTruthy();
    });
    expect(screen.queryByText("✓")).toBeNull();
  });

  it("does not mark model test as successful when the API request fails", async () => {
    authFetch.mockResolvedValue(response({ success: true }, { ok: false, status: 503, text: "down" }));

    renderModelPool();

    fireEvent.click(screen.getByRole("button", { name: "测试" }));

    expect(await screen.findByText("API 503: down")).toBeTruthy();
    expect(screen.queryByText("✓")).toBeNull();
  });

  it("does not toggle the model when persistence fails", async () => {
    const onToggle = vi.fn();
    authFetch.mockResolvedValue(response({}, { ok: false, status: 503, text: "down" }));

    const view = renderModelPool({ onToggle });

    const toggle = view.container.querySelector("button.w-8");
    expect(toggle).toBeTruthy();
    fireEvent.click(toggle as HTMLButtonElement);

    expect(await screen.findByText("模型保存失败：API 503: down")).toBeTruthy();
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("does not close custom model config when persistence fails", async () => {
    authFetch.mockResolvedValue(response({}, { ok: false, status: 500, text: "write failed" }));

    renderModelPool();

    fireEvent.click(screen.getByRole("button", { name: "配置" }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByText("配置保存失败：API 500: write failed")).toBeTruthy();
    expect(screen.getByRole("button", { name: "保存" })).toBeTruthy();
    expect(screen.queryByText("配置已保存")).toBeNull();
  });

  it("does not leak rejected custom config saves", async () => {
    authFetch.mockRejectedValue(new Error("network down"));

    renderModelPool();

    fireEvent.click(screen.getByRole("button", { name: "配置" }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByText("配置保存失败：network down")).toBeTruthy();
    expect(screen.getByRole("button", { name: "保存" })).toBeTruthy();
    expect(screen.queryByText("配置已保存")).toBeNull();
  });

  it("does not show add success when custom model add fails", async () => {
    renderModelPool({
      onAddCustomModel: vi.fn().mockRejectedValue(new Error("API 503: down")),
    });

    fireEvent.change(screen.getByPlaceholderText("搜索或输入模型 ID..."), {
      target: { value: "new:model" },
    });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "openai" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));

    expect(await screen.findByText("模型添加失败：API 503: down")).toBeTruthy();
    expect(screen.queryByText("模型已添加")).toBeNull();
  });

  it("does not swallow custom model remove failures", async () => {
    renderModelPool({
      onRemoveCustomModel: vi.fn().mockRejectedValue(new Error("API 503: down")),
    });

    fireEvent.click(screen.getByRole("button", { name: "移除" }));

    expect(await screen.findByText("模型移除失败：API 503: down")).toBeTruthy();
  });
});
