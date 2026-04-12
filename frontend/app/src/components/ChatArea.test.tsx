// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import ChatArea from "./ChatArea";

afterEach(() => {
  cleanup();
});

describe("ChatArea", () => {
  it("can shrink inside the chat flex column so the message pane owns scrolling", () => {
    const { container } = render(
      <ChatArea
        entries={[]}
        runtimeStatus={null}
        loading={false}
      />,
    );

    expect(container.firstElementChild?.className).toContain("min-h-0");
  });

  it("does not render hidden user entries", () => {
    render(
      <ChatArea
        entries={[
          {
            id: "hidden-user",
            role: "user",
            content: "<ask_user_question_answers>{}</ask_user_question_answers>",
            timestamp: Date.now(),
            showing: false,
          },
        ]}
        runtimeStatus={null}
        loading={false}
      />,
    );

    expect(screen.queryByText(/ask_user_question_answers/i)).toBeNull();
  });

  it("renders AskUserQuestion inline inside the assistant turn", () => {
    render(
      <ChatArea
        entries={[
          {
            id: "assistant-ask",
            role: "assistant",
            timestamp: Date.now(),
            segments: [
              {
                type: "tool",
                step: {
                  id: "ask-step",
                  name: "AskUserQuestion",
                  args: {},
                  status: "done",
                  timestamp: Date.now(),
                },
              },
            ],
          },
        ]}
        runtimeStatus={null}
        loading={false}
        askUserQuestion={{
          requestId: "req-1",
          promptMessage: "请先回答这个问题",
          prompts: [
            {
              header: "选择一个方向",
              question: "你希望我问什么？",
              options: [
                { label: "A", description: "简单问题" },
                { label: "B", description: "工作问题" },
              ],
            },
          ],
          selections: {},
          resolving: false,
          canSubmit: false,
          onSelect: () => undefined,
          onSubmit: () => undefined,
          selectionKeyForIndex: (index) => String(index),
        }}
      />,
    );

    expect(screen.getByText("等待回答")).toBeTruthy();
    expect(screen.getByText("选择一个方向")).toBeTruthy();
    expect(screen.getByRole("button", { name: "提交回答" })).toBeTruthy();
  });

  it("anchors hidden ask-user answers back onto the original assistant turn", () => {
    render(
      <ChatArea
        entries={[
          {
            id: "assistant-ask",
            role: "assistant",
            timestamp: Date.now(),
            segments: [
              {
                type: "tool",
                step: {
                  id: "ask-step",
                  name: "AskUserQuestion",
                  args: {},
                  status: "done",
                  timestamp: Date.now(),
                },
              },
            ],
          },
          {
            id: "hidden-user",
            role: "user",
            content:
              'The user answered your AskUserQuestion prompt. Continue the task using these answers.\n<ask_user_question_answers>\n{"questions":[{"header":"选择一个方向","question":"你希望我问什么？","options":[{"label":"A","description":"简单问题"},{"label":"B","description":"工作问题"}]}],"answers":[{"header":"选择一个方向","question":"你希望我问什么？","selected_options":["B"]}]}\n</ask_user_question_answers>',
            timestamp: Date.now() + 1,
            showing: false,
          },
        ]}
        runtimeStatus={null}
        loading={false}
      />,
    );

    expect(screen.queryByText(/ask_user_question_answers/i)).toBeNull();
    expect(screen.getByText(/已回答 · 选择一个方向：B/)).toBeTruthy();
    expect(screen.queryByText("你希望我问什么？")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "查看已回答详情" }));

    expect(screen.getByText("你希望我问什么？")).toBeTruthy();
    expect(screen.getByText("B")).toBeTruthy();
  });

  it("prefers explicit answered payload metadata over parsing hidden content", () => {
    render(
      <ChatArea
        entries={[
          {
            id: "assistant-ask",
            role: "assistant",
            timestamp: Date.now(),
            segments: [
              {
                type: "tool",
                step: {
                  id: "ask-step",
                  name: "AskUserQuestion",
                  args: {},
                  status: "done",
                  timestamp: Date.now(),
                },
              },
            ],
          },
          {
            id: "hidden-user",
            role: "user",
            content: "",
            timestamp: Date.now() + 1,
            showing: false,
            ask_user_question_answered: {
              questions: [
                {
                  header: "选择一个方向",
                  question: "你希望我问什么？",
                  options: [
                    { label: "A", description: "简单问题" },
                    { label: "B", description: "工作问题" },
                  ],
                },
              ],
              answers: [
                {
                  header: "选择一个方向",
                  question: "你希望我问什么？",
                  selected_options: ["A"],
                },
              ],
            },
          },
        ]}
        runtimeStatus={null}
        loading={false}
      />,
    );

    expect(screen.getByText(/已回答 · 选择一个方向：A/)).toBeTruthy();
  });
});
