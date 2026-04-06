import type { AskUserAnswer, AskUserQuestionPrompt } from "../api";

export interface AskUserQuestionPendingState {
  requestId: string;
  promptMessage: string;
  prompts: AskUserQuestionPrompt[];
  selections: Record<string, string[]>;
  resolving: boolean;
  canSubmit: boolean;
  onSelect: (questionIndex: number, question: AskUserQuestionPrompt, optionLabel: string) => void;
  onSubmit: () => void;
  selectionKeyForIndex: (questionIndex: number) => string;
}

export interface AskUserQuestionAnsweredPayload {
  questions: AskUserQuestionPrompt[];
  answers: AskUserAnswer[];
  annotations?: Record<string, unknown>;
}

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

export function parseAskUserQuestionAnswerPayload(content: string): AskUserQuestionAnsweredPayload | null {
  const match = content.match(/<ask_user_question_answers>\s*([\s\S]*?)\s*<\/ask_user_question_answers>/i);
  if (!match) return null;
  try {
    const parsed = JSON.parse(match[1]) as {
      questions?: AskUserQuestionPrompt[];
      answers?: AskUserAnswer[];
      annotations?: Record<string, unknown>;
    };
    if (!Array.isArray(parsed.questions) || !Array.isArray(parsed.answers)) return null;
    return {
      questions: parsed.questions,
      answers: parsed.answers,
      annotations: parsed.annotations,
    };
  } catch {
    return null;
  }
}
