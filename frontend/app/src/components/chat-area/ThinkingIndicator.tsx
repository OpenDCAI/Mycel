import { useEffect, useState } from "react";
import type { StreamStatus } from "../../api";

// Boot phase: agent is cold-starting (runtimeStatus still null)
const BOOT_MESSAGES = [
  "正在启动...",
  "加载工具链...",
  "初始化中间件...",
  "即将就绪...",
];

// Running phase: agent is warm, waiting for first content
const THINKING_MESSAGES = [
  "正在思考...",
  "分析中...",
  "规划行动...",
  "处理请求...",
];

interface ThinkingIndicatorProps {
  runtimeStatus?: StreamStatus | null;
}

export function ThinkingIndicator({ runtimeStatus }: ThinkingIndicatorProps) {
  const isBooting = !runtimeStatus;
  const phase = isBooting ? "boot" : "thinking";
  const messages = isBooting ? BOOT_MESSAGES : THINKING_MESSAGES;
  const [messageState, setMessageState] = useState({ phase, index: 0 });
  const msgIdx = messageState.phase === phase ? messageState.index : 0;

  useEffect(() => {
    const interval = setInterval(() => {
      setMessageState((prev) => ({
        phase,
        index: prev.phase === phase ? (prev.index + 1) % messages.length : 1 % messages.length,
      }));
    }, 1400);
    return () => clearInterval(interval);
  }, [phase, messages.length]);

  const tool = runtimeStatus?.current_tool;
  const orbClass = isBooting ? "thinking-orb thinking-orb-boot" : "thinking-orb";

  return (
    <div className="flex items-center gap-2 h-5">
      <div className="flex items-center gap-[3px]">
        <span className={orbClass} />
        <span className={orbClass} style={{ animationDelay: "140ms" }} />
        <span className={orbClass} style={{ animationDelay: "280ms" }} />
      </div>
      {tool ? (
        <span key={`tool-${tool}`} className="text-xs text-muted-foreground/70 animate-fade-in">
          使用 {tool}
        </span>
      ) : (
        <span key={`${phase}-${msgIdx}`} className="text-xs text-muted-foreground animate-fade-in">
          {messages[msgIdx]}
        </span>
      )}
    </div>
  );
}
