import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import type { AskUserQuestionPrompt } from "../api";

interface AskUserQuestionDialogProps {
  open: boolean;
  promptMessage: string;
  prompts: AskUserQuestionPrompt[];
  selections: Record<string, string[]>;
  resolving: boolean;
  canSubmit: boolean;
  onSelect: (questionIndex: number, question: AskUserQuestionPrompt, optionLabel: string) => void;
  onSubmit: () => void;
  selectionKeyForIndex: (questionIndex: number) => string;
}

export default function AskUserQuestionDialog({
  open,
  promptMessage,
  prompts,
  selections,
  resolving,
  canSubmit,
  onSelect,
  onSubmit,
  selectionKeyForIndex,
}: AskUserQuestionDialogProps) {
  return (
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent className="max-w-xl p-0 gap-0" showCloseButton={false}>
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-border/60">
          <DialogTitle className="text-base">回答问题</DialogTitle>
          <DialogDescription className="text-sm leading-6">
            {promptMessage || "Leon 需要你的回答后才能继续当前任务。"}
          </DialogDescription>
        </DialogHeader>
        <div className="px-6 py-5 space-y-4 max-h-[70vh] overflow-y-auto" data-testid="ask-user-question-dialog">
          {prompts.map((question, index) => {
            const selected = selections[selectionKeyForIndex(index)] ?? [];
            return (
              <section
                key={`${question.header}:${index}`}
                className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-3"
              >
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-foreground">{question.header}</p>
                  <p className="text-sm text-muted-foreground">{question.question}</p>
                </div>
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
              </section>
            );
          })}
        </div>
        <DialogFooter className="px-6 py-4 border-t border-border/60">
          <Button onClick={onSubmit} disabled={resolving || !canSubmit}>
            提交回答
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
