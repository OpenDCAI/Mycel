import type { StreamEvent, StreamEventType } from "./types";
import { STREAM_EVENT_TYPES } from "./types";

const VALID_EVENT_TYPES: ReadonlySet<string> = new Set(STREAM_EVENT_TYPES);

function isStreamEventType(raw: string): raw is StreamEventType {
  return VALID_EVENT_TYPES.has(raw);
}

function normalizeStreamType(raw: string): StreamEventType {
  if (isStreamEventType(raw)) return raw;
  console.warn(`[SSE] Unknown event type: "${raw}", falling back to "text"`);
  return "text";
}

function tryParse(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function extractSeq(data: unknown): number | undefined {
  if (isRecord(data)) {
    const seq = data._seq;
    if (typeof seq === "number") return seq;
  }
  return undefined;
}

function parseSSEChunk(chunk: string): { eventType: string; dataRaw: string } | null {
  if (!chunk.trim()) return null;
  let eventType = "text";
  const dataLines: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) eventType = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  return { eventType, dataRaw: dataLines.join("\n") };
}

export function processChunk(
  chunk: string,
  onEvent: (event: StreamEvent) => void,
  seq: number,
): { seq: number; runEnded: boolean } {
  const parsed = parseSSEChunk(chunk);
  if (!parsed || (!parsed.dataRaw && parsed.eventType === "text")) return { seq, runEnded: false };
  const type = normalizeStreamType(parsed.eventType);
  const data = tryParse(parsed.dataRaw);
  const newSeq = extractSeq(data) ?? seq;
  onEvent({ type, data });
  // run_done is an in-band signal — the connection stays open
  return { seq: newSeq, runEnded: type === "run_done" };
}
