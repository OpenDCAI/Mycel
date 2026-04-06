// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ChatArea from "./ChatArea";

describe("ChatArea", () => {
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
});
