// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CenteredInputBox from "./CenteredInputBox";

describe("CenteredInputBox", () => {
  it("shows backend send errors without clearing the draft message", async () => {
    const onSend = vi.fn(async () => {
      throw new Error("Self-host Daytona sandbox quota exceeded");
    });

    render(
      <CenteredInputBox
        environmentControl={{ summary: <span>local</span>, renderPanel: () => null }}
        onSend={onSend}
      />,
    );

    const input = screen.getByPlaceholderText("告诉 Mycel 你需要什么帮助...");
    fireEvent.change(input, { target: { value: "run the trial" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("Self-host Daytona sandbox quota exceeded")).toBeTruthy();
    expect((input as HTMLTextAreaElement).value).toBe("run the trial");
  });
});
