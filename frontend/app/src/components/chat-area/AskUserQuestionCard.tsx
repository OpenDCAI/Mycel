import { CheckCircle2, ChevronDown, ChevronRight, Clock } from "lucide-react";
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
    <span className="text-xs text-muted-foreground truncate">
      已回答 · {summary.join(" · ")}
    </span>
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
    <div className="space-y-1.5">
      {question.options.map((option) => {
        const active = selected.includes(option.label);
        return (
          <button
            key={option.label}
            type="button"
            className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
              active
                ? "border-primary bg-primary/10 text-foreground"
                : "border-border/60 bg-background hover:border-primary/40 hover:bg-muted/40"
            }`}
            onClick={() => onSelect(index, question, option.label)}
          >
            <div className="text-sm font-medium">{option.label}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{option.description}</div>
            {option.preview ? (
              <div className="text-xs text-muted-foreground/80 mt-1">{option.preview}</div>
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
      <section className="rounded-lg border border-border bg-muted px-4 py-3 space-y-3">
        <div className="space-y-1">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-amber-500" />
            <span className="text-xs font-medium text-foreground">等待回答</span>
          </div>
          <p className="text-xs text-muted-foreground">
            {pending.promptMessage || "Leon 需要你的回答后才能继续当前任务。"}
          </p>
        </div>

        <div className="space-y-3">
          {pending.prompts.map((question, index) => {
            const selected = pending.selections[pending.selectionKeyForIndex(index)] ?? [];
            return (
              <section
                key={`${question.header}:${index}`}
                className={index > 0 ? "border-t border-border/60 pt-3" : ""}
              >
                <div className="space-y-1 mb-2">
                  <p className="text-sm font-medium text-foreground">{question.header}</p>
                  <p className="text-xs text-muted-foreground">{question.question}</p>
                </div>
                <QuestionChoices question={question} index={index} selected={selected} onSelect={pending.onSelect} />
              </section>
            );
          })}
        </div>

        <div className="flex items-center justify-end">
          <Button size="sm" onClick={pending.onSubmit} disabled={pending.resolving || !pending.canSubmit}>
            提交回答
          </Button>
        </div>
      </section>
    );
  }

  const { answered } = props;
  return (
    <section className="rounded-lg border border-border bg-muted/50 px-3 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 min-w-0">
          <CheckCircle2 className="w-3 h-3 text-muted-foreground/70 flex-shrink-0" />
          <AnsweredSummary answered={answered} />
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-0.5 text-2xs text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
          aria-label={expanded ? "收起已回答详情" : "查看已回答详情"}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          {expanded ? "收起" : "详情"}
        </button>
      </div>

      {expanded && (
        <div className="mt-2.5 space-y-3">
          {answered.questions.map((question, index) => {
            const answer = answered.answers[index];
            const selectedOptions = new Set(answer?.selected_options ?? []);
            return (
              <section
                key={`${question.header}:${index}`}
                className={index > 0 ? "border-t border-border/60 pt-3" : ""}
              >
                <div className="space-y-1 mb-2">
                  <p className="text-sm font-medium text-foreground">{question.header}</p>
                  <p className="text-xs text-muted-foreground">{question.question}</p>
                </div>
                <div className="space-y-1.5">
                  {question.options.map((option) => {
                    const active = selectedOptions.has(option.label);
                    return (
                      <div
                        key={option.label}
                        className={`rounded-lg border px-3 py-2 ${
                          active
                            ? "border-primary/40 bg-primary/5 text-foreground"
                            : "border-border/60 bg-background text-muted-foreground"
                        }`}
                      >
                        <div className="text-sm font-medium">{option.label}</div>
                        <div className="text-xs mt-0.5">{option.description}</div>
                        {option.preview ? <div className="text-xs mt-1 opacity-80">{option.preview}</div> : null}
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
