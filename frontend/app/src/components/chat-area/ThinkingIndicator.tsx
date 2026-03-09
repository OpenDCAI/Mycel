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
  const messages = isBooting ? BOOT_MESSAGES : THINKING_MESSAGES;
  const [msgIdx, setMsgIdx] = useState(0);

  // Reset index when switching between boot and thinking phases
  useEffect(() => {
    setMsgIdx(0);
  }, [isBooting]);

  useEffect(() => {
    const interval = setInterval(() => {
      setMsgIdx((prev) => (prev + 1) % messages.length);
    }, 1400);
    return () => clearInterval(interval);
  }, [messages]);

  const tool = runtimeStatus?.current_tool;
  const orbClass = isBooting ? "thinking-orb thinking-orb-boot" : "thinking-orb";

  return (
    <div className="flex items-center gap-2 h-5">
      <div className="flex items-center gap-[3px]">
        <span className={orbClass} />
        <span className={orbClass} style={{ animationDelay: "0.14s" }} />
        <span className={orbClass} style={{ animationDelay: "0.28s" }} />
      </div>
      {tool ? (
        <span key={`tool-${tool}`} className="text-[12px] text-[#a3a3a3] animate-fade-in">
          使用 {tool}
        </span>
      ) : (
        <span key={`${isBooting ? "boot" : "think"}-${msgIdx}`} className="text-[12px] text-[#737373] animate-fade-in">
          {messages[msgIdx]}
        </span>
      )}
    </div>
  );
}
