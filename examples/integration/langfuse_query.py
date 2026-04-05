"""Langfuse query tool — fetch and format session/trace data by thread ID.

Usage:
    python scripts/langfuse_query.py traces [N]
    python scripts/langfuse_query.py session <thread_id>
    python scripts/langfuse_query.py trace <trace_id>
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from langfuse.api.client import FernLangfuse

_OBS_FILE = Path.home() / ".leon" / "observation.json"
_TRUNC = 120


def _client() -> FernLangfuse:
    if not _OBS_FILE.exists():
        raise SystemExit("No ~/.leon/observation.json found")
    cfg = json.loads(_OBS_FILE.read_text())["langfuse"]
    return FernLangfuse(
        username=cfg["public_key"],
        password=cfg["secret_key"],
        base_url=cfg.get("host", "https://cloud.langfuse.com"),
    )


def _ts(t: datetime | None) -> str:
    return t.strftime("%H:%M:%S.%f")[:-3] if t else "?"


def _dur(s: datetime | None, e: datetime | None) -> str:
    if not s or not e:
        return "?"
    ms = (e - s).total_seconds() * 1000
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _trunc(s: str, n: int = _TRUNC) -> str:
    return s[:n] + "..." if len(s) > n else s


def _summarize_messages(msgs: list, first: bool = False) -> str:
    """Extract key info from LangChain message list."""
    # Filter out tool-definition entries (role=tool but content is dict)
    real_msgs = [m for m in msgs if not (m.get("role") == "tool" and isinstance(m.get("content"), dict))]

    if first:
        parts = []
        for m in real_msgs:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, list):
                texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                content = " ".join(texts)
            if role == "system":
                parts.append(f"[system] {_trunc(content, 80)}")
            elif role == "user":
                parts.append(f"[user] {_trunc(content, 100)}")
                break
        return "\n".join(parts)

    # Subsequent calls: show last tool results only
    parts = []
    for m in real_msgs[-3:]:
        role = m.get("role", "?")
        content = m.get("content", "")
        if role == "tool":
            parts.append(f"[tool] {_trunc(str(content), 80)}")
    return "\n".join(parts) if parts else "(context from previous turns)"


def _fmt_usage(u, details=None) -> str:
    if not u:
        return ""
    parts = []
    if u.input:
        cache_read = details.get("input_cache_read", 0) if details else 0
        if cache_read:
            parts.append(f"in={u.input}(cached={cache_read})")
        else:
            parts.append(f"in={u.input}")
    if u.output:
        reasoning = details.get("output_reasoning", 0) if details else 0
        if reasoning:
            parts.append(f"out={u.output}(reasoning={reasoning})")
        else:
            parts.append(f"out={u.output}")
    if u.total:
        parts.append(f"total={u.total}")
    return " ".join(parts) if parts else ""


def list_traces(limit: int = 10):
    c = _client()
    for t in c.trace.list(limit=limit).data:
        print(f"{t.id[:12]}  {_ts(t.timestamp)}  {t.name or '-':<15}  session={t.session_id or '-'}")


def show_session(thread_id: str):
    c = _client()
    traces = c.trace.list(session_id=thread_id, limit=50)
    if not traces.data:
        print(f"No traces for session {thread_id}")
        return

    print(f"═══ Session: {thread_id}")
    print(f"    Traces: {len(traces.data)}\n")

    for t in sorted(traces.data, key=lambda x: x.timestamp or datetime.min):
        obs_list = c.observations.get_many(trace_id=t.id, limit=100)
        obs_sorted = sorted(obs_list.data, key=lambda x: x.start_time or datetime.min)

        # Compute total duration
        total_dur = _dur(t.timestamp, obs_sorted[-1].end_time if obs_sorted and obs_sorted[-1].end_time else None)
        print(f"── Trace {t.id[:12]}  {_ts(t.timestamp)}  total={total_dur}")

        step = 0
        for o in obs_sorted:
            dur = _dur(o.start_time, o.end_time)

            if o.type == "GENERATION":
                step += 1
                usage = _fmt_usage(o.usage, o.usage_details)
                print(f"\n  [{step}] LLM  {o.model or '?':<25} {dur:>8}  {usage}")
                # Show input: first call shows system+user, subsequent only last 3 messages
                if o.input and isinstance(o.input, list):
                    msgs = [m for m in o.input if isinstance(m, dict) and "role" in m]
                    summary = _summarize_messages(msgs, first=(step == 1))
                    for line in summary.split("\n"):
                        print(f"      {line}")
                # Show output summary
                if o.output and isinstance(o.output, dict):
                    content = o.output.get("content", "")
                    tc = o.output.get("tool_calls", [])
                    if tc:
                        calls = ", ".join(
                            f"{c.get('name') or c.get('function',{}).get('name','?')}({_trunc(json.dumps(c.get('args') or c.get('function',{}).get('arguments',{}), ensure_ascii=False), 60)})"
                            for c in tc
                        )
                        print(f"      → {calls}")
                    elif content:
                        print(f"      ← {_trunc(content, 100)}")

            elif o.type == "TOOL":
                print(f"  ... tool  {o.name or '?':<25} {dur:>8}")
                if o.input:
                    inp = json.dumps(o.input, ensure_ascii=False) if not isinstance(o.input, str) else o.input
                    print(f"      args: {_trunc(inp, 100)}")
                if o.output:
                    out = json.dumps(o.output, ensure_ascii=False) if not isinstance(o.output, str) else o.output
                    print(f"      result: {_trunc(out, 100)}")

            # Skip CHAIN/AGENT noise

        print(f"\n  ── end ({total_dur})\n")


def show_trace(trace_id: str):
    """Alias: show same as session but for a single trace."""
    c = _client()
    t = c.trace.get(trace_id)
    print(f"Trace: {t.id}")
    print(f"Session: {t.session_id}")
    # Reuse session display for the single trace
    if t.session_id:
        show_session(t.session_id)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "traces":
        list_traces(int(sys.argv[2]) if len(sys.argv) > 2 else 10)
    elif cmd == "session":
        if len(sys.argv) < 3:
            print("Usage: session <thread_id>")
            return
        show_session(sys.argv[2])
    elif cmd == "trace":
        if len(sys.argv) < 3:
            print("Usage: trace <trace_id>")
            return
        show_trace(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
