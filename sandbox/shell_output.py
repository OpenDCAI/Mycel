"""Shared shell/PTY output normalization helpers."""

from __future__ import annotations

import re


def normalize_pty_result(output: str, command: str | None = None) -> str:
    lines = output.splitlines()
    if not lines:
        return output.strip()

    command_hint = command.strip().splitlines()[0].strip() if command else ""
    compact_command = re.sub(r"\s+", " ", command_hint)

    filtered: list[str] = []
    dropped_echo = False
    for line in lines:
        stripped = line.strip()
        if "__LEON_PTY_END_" in stripped:
            continue
        if compact_command and not dropped_echo:
            compact_line = re.sub(r"\s+", " ", stripped)
            if compact_command in compact_line and compact_line.endswith(">"):
                prefix = compact_line.split(compact_command, 1)[0]
                if (
                    not prefix
                    or re.search(r"[^A-Za-z0-9_./~:-]", prefix)
                    or (len(prefix) <= 2 and compact_command.startswith(prefix))
                ):
                    dropped_echo = True
                    continue
        filtered.append(line)

    while filtered and re.fullmatch(r"\s*[%#$>]\s*", filtered[-1]):
        filtered.pop()
    while filtered and not filtered[0].strip():
        filtered.pop(0)

    return "\n".join(filtered).strip()
