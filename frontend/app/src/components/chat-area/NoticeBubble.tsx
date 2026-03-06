import { CheckCircle2, XCircle, Clock, Terminal, Bot } from "lucide-react";
import type { NoticeMessage, NotificationType } from "../../api";

interface NoticeBubbleProps {
  entry: NoticeMessage;
  onTaskNoticeClick?: (taskId: string) => void;
}

export interface ParsedNotice {
  text: string;
  status?: "completed" | "error" | "pending";
  taskId?: string;
  commandLine?: string;
}

const STATUS_ICON = {
  completed: <CheckCircle2 className="w-3 h-3 text-emerald-500 shrink-0" />,
  error: <XCircle className="w-3 h-3 text-red-400 shrink-0" />,
  pending: <Clock className="w-3 h-3 text-gray-400 shrink-0" />,
} as const;

// --- Steer: right-aligned bubble (user injected a message while AI was working) ---

function SteerBubble({ parsed }: { parsed: ParsedNotice }) {
  if (!parsed.text) return null;
  return (
    <div className="flex justify-end animate-fade-in">
      <div className="max-w-[78%]">
        <div className="rounded-xl rounded-br-sm px-3.5 py-2 bg-amber-50 border border-amber-200/60">
          <div className="text-[10px] text-amber-500 font-medium mb-0.5">Steer</div>
          <p className="text-[13px] whitespace-pre-wrap leading-[1.55] text-[#171717]">
            {parsed.text}
          </p>
        </div>
      </div>
    </div>
  );
}

// --- Command: centered divider with terminal icon ---

function CommandDivider({ parsed, inline }: { parsed: ParsedNotice; inline?: boolean }) {
  if (!parsed.text) return null;
  const statusIcon = parsed.status ? STATUS_ICON[parsed.status] : null;
  return (
    <div className={`flex items-center gap-3 ${inline ? "my-2" : "my-3"} select-none`}>
      <div className="flex-1 h-px bg-gray-100" />
      <span className="inline-flex items-center gap-1.5 px-2.5 text-[11px] text-gray-400">
        <Terminal className="w-3 h-3 shrink-0" />
        {statusIcon}
        {parsed.text}
      </span>
      <div className="flex-1 h-px bg-gray-100" />
    </div>
  );
}

// --- Agent: centered divider with bot icon, clickable to focus ---

function AgentDivider({ parsed, inline, onClick }: { parsed: ParsedNotice; inline?: boolean; onClick?: () => void }) {
  if (!parsed.text) return null;
  const statusIcon = parsed.status ? STATUS_ICON[parsed.status] : null;
  const isClickable = !!onClick;

  const content = (
    <span className={`inline-flex items-center gap-1.5 px-2.5 text-[11px] text-gray-400 ${
      isClickable ? "hover:text-gray-600 transition-colors cursor-pointer" : ""
    }`}>
      <Bot className="w-3 h-3 shrink-0" />
      {statusIcon}
      {parsed.text}
    </span>
  );

  return (
    <div className={`flex items-center gap-3 ${inline ? "my-2" : "my-3"} select-none`}>
      <div className="flex-1 h-px bg-gray-100" />
      {isClickable ? (
        <button onClick={onClick}>{content}</button>
      ) : (
        content
      )}
      <div className="flex-1 h-px bg-gray-100" />
    </div>
  );
}

// --- Generic fallback divider (no notification_type) ---

function GenericDivider({ parsed, inline }: { parsed: ParsedNotice; inline?: boolean }) {
  if (!parsed.text) return null;
  return (
    <div className={`flex items-center gap-3 ${inline ? "my-2" : "my-3"} select-none`}>
      <div className="flex-1 h-px bg-gray-100" />
      <span className="inline-flex items-center gap-1.5 px-2.5 text-[11px] text-gray-400">
        {parsed.text}
      </span>
      <div className="flex-1 h-px bg-gray-100" />
    </div>
  );
}

// --- Public components ---

/**
 * Standalone notice rendered between chat entries.
 */
export function NoticeBubble({ entry, onTaskNoticeClick }: NoticeBubbleProps) {
  const ntype = entry.notification_type;
  const parsed = parseNoticeContent(entry.content, ntype);
  return renderNotice(parsed, ntype, {
    inline: false,
    onTaskClick: parsed.taskId && onTaskNoticeClick ? () => onTaskNoticeClick(parsed.taskId!) : undefined,
  });
}

/**
 * Inline notice rendered within an assistant block (between phases).
 */
export function InlineNotice({ content, notificationType, onTaskClick }: {
  content: string;
  notificationType?: NotificationType;
  onTaskClick?: (taskId: string) => void;
}) {
  const parsed = parseNoticeContent(content, notificationType);
  return renderNotice(parsed, notificationType, {
    inline: true,
    onTaskClick: parsed.taskId && onTaskClick ? () => onTaskClick(parsed.taskId!) : undefined,
  });
}

function renderNotice(
  parsed: ParsedNotice,
  notificationType: NotificationType | undefined,
  opts: { inline: boolean; onTaskClick?: () => void },
) {
  if (!parsed.text) return null;

  switch (notificationType) {
    case "steer":
      return <SteerBubble parsed={parsed} />;
    case "command":
      return <CommandDivider parsed={parsed} inline={opts.inline} />;
    case "agent":
      return <AgentDivider parsed={parsed} inline={opts.inline} onClick={opts.onTaskClick} />;
    default:
      return <GenericDivider parsed={parsed} inline={opts.inline} />;
  }
}

// --- Parsing ---

function normalizeStatus(raw: string): ParsedNotice["status"] {
  const lower = raw.toLowerCase().trim();
  if (lower === "completed" || lower === "done" || lower === "success") return "completed";
  if (lower === "error" || lower === "failed") return "error";
  return "pending";
}

export function parseNoticeContent(raw: string, notificationType?: NotificationType): ParsedNotice {
  switch (notificationType) {
    case "steer":
      return parseSteer(raw);
    case "command":
      return parseCommand(raw);
    case "agent":
      return parseAgent(raw);
    default:
      return { text: raw.replace(/<[^>]+>/g, "").trim() };
  }
}

function parseSteer(raw: string): ParsedNotice {
  const match = raw.match(/The user sent a new message while you were working:\n([\s\S]*?)\n\nIMPORTANT:/);
  if (match) return { text: match[1].trim() };
  return { text: raw.replace(/<[^>]+>/g, "").trim() };
}

function unescapeXml(s: string): string {
  return s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#x27;/g, "'");
}

function parseCommand(raw: string): ParsedNotice {
  const statusRaw = raw.match(/<Status>([\s\S]*?)<\/Status>/)?.[1]?.trim() ?? "";
  const commandLine = unescapeXml(raw.match(/<CommandLine>([\s\S]*?)<\/CommandLine>/)?.[1]?.trim() ?? "");
  const description = raw.match(/<Description>([\s\S]*?)<\/Description>/)?.[1]?.trim();
  const status = normalizeStatus(statusRaw);
  const label = description ? unescapeXml(description) : commandLine || "Command";
  const statusText = status === "completed" ? "done" : status === "error" ? "failed" : statusRaw;
  return { text: `${label} ${statusText}`, status, commandLine: commandLine || undefined };
}

function parseAgent(raw: string): ParsedNotice {
  const taskId = raw.match(/<task-id>([\s\S]*?)<\/task-id>/)?.[1]?.trim() ?? "";
  const statusRaw = raw.match(/<status>([\s\S]*?)<\/status>/)?.[1]?.trim() ?? "";
  const description = raw.match(/<description>([\s\S]*?)<\/description>/)?.[1]?.trim() ?? "";
  const status = normalizeStatus(statusRaw);
  const label = description || `Task ${taskId}`;
  const statusText = status === "completed" ? "done" : status === "error" ? "failed" : statusRaw;
  return { text: `${label} ${statusText}`, status, taskId: taskId || undefined };
}
