import { useState } from "react";
import { X, Send, Bot, Circle } from "lucide-react";

interface Props {
  memberName: string;
  onClose: () => void;
}

export default function TestPanel({ memberName, onClose }: Props) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);

  const mockResponses = [
    (msg: string) => `[${memberName}] 收到你的消息: "${msg}"。这是一条模拟回复。`,
    (msg: string) => `[${memberName}] 正在处理你的请求: "${msg}"。请稍候...分析完成，一切正常。`,
    (msg: string) => `[${memberName}] 已理解指令。关于 "${msg}"，我建议分步骤执行以确保质量。`,
    (msg: string) => `[${memberName}] 好的，我来处理 "${msg}"。预计需要几分钟时间完成。`,
    (msg: string) => `[${memberName}] 收到！"${msg}" 这个任务我很擅长，马上开始。`,
  ];

  const handleSend = () => {
    if (!input.trim()) return;
    const userMsg = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setInput("");
    setTimeout(() => {
      const pick = mockResponses[Math.floor(Math.random() * mockResponses.length)];
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: pick(userMsg) },
      ]);
    }, 800);
  };

  return (
    <div className="w-full md:w-[360px] shrink-0 border-l border-border bg-card flex flex-col h-full">
      <div className="h-12 flex items-center justify-between px-4 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <Circle className="w-2 h-2 fill-success text-success" />
          <span className="text-sm font-medium text-foreground">测试面板</span>
        </div>
        <button onClick={onClose} className="p-1 rounded-md hover:bg-muted transition-colors duration-fast">
          <X className="w-4 h-4 text-muted-foreground" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-10 h-10 rounded-xl bg-primary/8 flex items-center justify-center mb-3">
              <Bot className="w-5 h-5 text-primary" />
            </div>
            <p className="text-sm text-muted-foreground">发送消息测试 {memberName}</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] px-3 py-2 rounded-lg text-sm ${
              msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
      </div>

      <div className="p-3 border-t border-border shrink-0">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="输入测试消息..."
            className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-sm outline-none focus:border-primary/40 transition-colors duration-fast"
          />
          <button onClick={handleSend} disabled={!input.trim()} className="p-2 rounded-lg bg-primary text-primary-foreground disabled:opacity-50 hover:opacity-90 transition-opacity duration-fast">
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
