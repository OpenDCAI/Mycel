import { ChevronDown, ChevronRight, CircleCheckBig } from "lucide-react";
import { useMemo, useState } from "react";
import type { AskUserQuestionPrompt } from "../../api";
import type { AskUserQuestionAnsweredPayload, AskUserQuestionPendingState } from "../../pages/ask-user-question";
import { Button } from "../ui/button";

type AskUserQuestionCardProps =
  | {
      mode: "pending";
      pending: AskUserQuestionPendingState;
    }
  | {
      mode: "answered";
      answered: AskUserQuestionAnsweredPayload;
    };

function AnsweredSummary({ answered }: { answered: AskUserQuestionAnsweredPayload }) {
  const summary = useMemo(
    () =>
      answered.answers.map((answer, index) => {
        const header = answer.header || answered.questions[index]?.header || `问题 ${index + 1}`;
        const selected = answer.selected_options.join("、") || "未选择";
        return `${header}：${selected}`;
      }),
    [answered],
  );

  return (
    <div className="space-y-1">
      <p className="text-sm font-semibold text-foreground">已回答问题</p>
      {summary.map((line) => (
        <p key={line} className="text-sm text-muted-foreground">
          {line}
        </p>
      ))}
    </div>
  );
}

function QuestionChoices({
  question,
  index,
  selected,
  onSelect,
}: {
  question: AskUserQuestionPrompt;
  index: number;
  selected: string[];
  onSelect: (questionIndex: number, question: AskUserQuestionPrompt, optionLabel: string) => void;
}) {
  return (
    <div className="space-y-2">
      {question.options.map((option) => {
        const active = selected.includes(option.label);
        return (
          <button
            key={option.label}
            type="button"
            className={`w-full rounded-xl border px-4 py-3 text-left transition-colors ${
              active
                ? "border-primary bg-primary/10 text-foreground"
                : "border-border/60 bg-background hover:border-primary/40 hover:bg-muted/40"
            }`}
            onClick={() => onSelect(index, question, option.label)}
          >
            <div className="text-sm font-medium">{option.label}</div>
            <div className="text-xs text-muted-foreground mt-1">{option.description}</div>
            {option.preview ? (
              <div className="text-xs text-muted-foreground/80 mt-2">{option.preview}</div>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function AskUserQuestionCard(props: AskUserQuestionCardProps) {
  const [expanded, setExpanded] = useState(props.mode === "pending");

  if (props.mode === "pending") {
    const { pending } = props;
    return (
      <section className="rounded-2xl border border-amber-300/60 bg-amber-50/50 px-4 py-4 space-y-4">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-foreground">回答问题</p>
          <p className="text-sm text-muted-foreground">
            {pending.promptMessage || "Leon 需要你的回答后才能继续当前任务。"}
          </p>
        </div>

        <div className="space-y-4">
          {pending.prompts.map((question, index) => {
            const selected = pending.selections[pending.selectionKeyForIndex(index)] ?? [];
            return (
              <section key={`${question.header}:${index}`} className="rounded-xl border border-border/60 bg-background/70 p-4 space-y-3">
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-foreground">{question.header}</p>
                  <p className="text-sm text-muted-foreground">{question.question}</p>
                </div>
                <QuestionChoices question={question} index={index} selected={selected} onSelect={pending.onSelect} />
              </section>
            );
          })}
        </div>

        <div className="flex items-center justify-end">
          <Button onClick={pending.onSubmit} disabled={pending.resolving || !pending.canSubmit}>
            提交回答
          </Button>
        </div>
      </section>
    );
  }

  const { answered } = props;
  return (
    <section className="rounded-2xl border border-emerald-300/60 bg-emerald-50/50 px-4 py-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <CircleCheckBig className="w-4 h-4 mt-0.5 text-emerald-600" />
          <AnsweredSummary answered={answered} />
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          aria-label={expanded ? "收起已回答详情" : "查看已回答详情"}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          {expanded ? "收起" : "详情"}
        </button>
      </div>

      {expanded && (
        <div className="space-y-4">
          {answered.questions.map((question, index) => {
            const answer = answered.answers[index];
            const selectedOptions = new Set(answer?.selected_options ?? []);
            return (
              <section key={`${question.header}:${index}`} className="rounded-xl border border-border/60 bg-background/80 p-4 space-y-3">
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-foreground">{question.header}</p>
                  <p className="text-sm text-muted-foreground">{question.question}</p>
                </div>
                <div className="space-y-2">
                  {question.options.map((option) => {
                    const active = selectedOptions.has(option.label);
                    return (
                      <div
                        key={option.label}
                        className={`rounded-xl border px-4 py-3 ${
                          active
                            ? "border-emerald-400/70 bg-emerald-100/60 text-foreground"
                            : "border-border/60 bg-background text-muted-foreground"
                        }`}
                      >
                        <div className="text-sm font-medium">{option.label}</div>
                        <div className="text-xs mt-1">{option.description}</div>
                        {option.preview ? <div className="text-xs mt-2 opacity-80">{option.preview}</div> : null}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}
