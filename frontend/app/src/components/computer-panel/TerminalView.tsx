import { useEffect, useRef } from "react";
import type { ToolStep } from "../../api";
import { parseCommandArgs } from "./utils";

export function TerminalView({ steps }: { steps: ToolStep[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [steps]);

  return (
    <div
      ref={scrollRef}
      className="h-full overflow-auto font-mono text-[13px] leading-[1.6] p-4"
      style={{ background: "#1e1e1e", color: "#d4d4d4" }}
    >
      {/* Boot banner */}
      <div style={{ color: "#6a9955" }} className="mb-3 select-none">
        <div>Mycel Terminal v1.0</div>
        <div className="text-[11px]" style={{ color: "#555" }}>Type is streamed from agent tool calls</div>
        <div className="mt-1" style={{ color: "#333" }}>{"─".repeat(48)}</div>
      </div>

      {steps.length === 0 && <TerminalCursor />}

      {steps.map((step) => (
        <TerminalStep key={step.id} step={step} />
      ))}

      {/* Cursor at bottom if last command is done */}
      {steps.length > 0 && steps[steps.length - 1].status !== "calling" && <TerminalCursor />}
    </div>
  );
}

function TerminalStep({ step }: { step: ToolStep }) {
  const { command, cwd } = parseCommandArgs(step.args);
  const dir = cwd || "~";
  const shortDir = dir === "/" ? "/" : dir.split("/").pop() || dir;

  return (
    <div className="mb-3">
      {/* Prompt line */}
      <div className="flex flex-wrap">
        <span style={{ color: "#6a9955" }}>leon@sandbox</span>
        <span style={{ color: "#d4d4d4" }}>:</span>
        <span style={{ color: "#569cd6" }}>{shortDir}</span>
        <span style={{ color: "#d4d4d4" }}>$ </span>
        <span style={{ color: "#ce9178" }}>{command || "(empty)"}</span>
      </div>

      {/* Output */}
      {step.status === "calling" ? (
        <div className="mt-0.5" style={{ color: "#555" }}>
          <span className="animate-pulse">...</span>
        </div>
      ) : step.result ? (
        <pre className="mt-0.5 whitespace-pre-wrap break-words" style={{ color: "#cccccc" }}>
          {step.result}
        </pre>
      ) : (
        <div className="mt-0.5" style={{ color: "#555" }}>(no output)</div>
      )}

      {/* Exit indicator for errors */}
      {step.status === "error" && (
        <div style={{ color: "#f44747" }} className="mt-0.5">
          [exit: error]
        </div>
      )}
    </div>
  );
}

function TerminalCursor() {
  return (
    <div>
      <span style={{ color: "#6a9955" }}>leon@sandbox</span>
      <span style={{ color: "#d4d4d4" }}>:</span>
      <span style={{ color: "#569cd6" }}>~</span>
      <span style={{ color: "#d4d4d4" }}>$ </span>
      <span className="animate-pulse">_</span>
    </div>
  );
}
