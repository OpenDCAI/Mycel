import { describe, expect, it } from "vitest";
import { askUserQuestionSelectionKey, buildAskUserAnswers } from "./ask-user-question";
import type { AskUserQuestionPrompt } from "../api";

describe("ask-user-question helpers", () => {
  it("keeps duplicate prompts independently addressable by position", () => {
    const questions: AskUserQuestionPrompt[] = [
      {
        header: "Style",
        question: "Choose a style",
        options: [{ label: "Minimal", description: "Keep it simple" }],
      },
      {
        header: "Style",
        question: "Choose a style",
        options: [{ label: "Bold", description: "Make it loud" }],
      },
    ];

    const answers = buildAskUserAnswers(questions, {
      [askUserQuestionSelectionKey(0)]: ["Minimal"],
      [askUserQuestionSelectionKey(1)]: ["Bold"],
    });

    expect(answers).toEqual([
      {
        header: "Style",
        question: "Choose a style",
        selected_options: ["Minimal"],
      },
      {
        header: "Style",
        question: "Choose a style",
        selected_options: ["Bold"],
      },
    ]);
  });
});
