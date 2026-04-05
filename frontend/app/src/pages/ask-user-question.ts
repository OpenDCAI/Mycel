import type { AskUserAnswer, AskUserQuestionPrompt } from "../api";

export function askUserQuestionSelectionKey(questionIndex: number): string {
  return String(questionIndex);
}

export function buildAskUserAnswers(
  questions: AskUserQuestionPrompt[],
  selections: Record<string, string[]>,
): AskUserAnswer[] {
  return questions.map((question, index) => ({
    header: question.header,
    question: question.question,
    selected_options: selections[askUserQuestionSelectionKey(index)] ?? [],
  }));
}
