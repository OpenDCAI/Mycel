"""Dangerous commands hook - blocks commands that may harm the system."""

import re
import shlex
from pathlib import Path
from typing import Any

from .base import BashHook, HookResult


class DangerousCommandsHook(BashHook):
    """Dangerous commands hook - blocks destructive system commands."""

    priority = 5
    name = "DangerousCommands"
    description = "Block dangerous commands that may harm the system"
    enabled = True

    DEFAULT_BLOCKED_COMMANDS = [
        r"\brm\s+-rf",
        r"\brm\s+.*-.*r.*f",
        r"\brmdir\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"\bsudo\b",
        r"\bsu\b",
        r"\bkill\b",
        r"\bpkill\b",
        r"\breboot\b",
        r"\bshutdown\b",
        r"\bmkfs\b",
        r"\bdd\b",
    ]

    NETWORK_COMMANDS = [
        r"\bcurl\b",
        r"\bwget\b",
        r"\bscp\b",
        r"\bsftp\b",
        r"\brsync\b",
        r"\bssh\b",
    ]

    DEFAULT_BLOCKED_BASE_COMMANDS = {
        "rmdir",
        "chmod",
        "chown",
        "sudo",
        "su",
        "kill",
        "pkill",
        "reboot",
        "shutdown",
        "mkfs",
        "dd",
    }
    NETWORK_BASE_COMMANDS = {
        "curl",
        "wget",
        "scp",
        "sftp",
        "rsync",
        "ssh",
    }
    OPERATOR_TOKENS = {";", ";;", "&", "&&", "|", "||", "(", ")"}
    ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")
    ANSI_C_QUOTE_RE = re.compile(r"\$'[^']*'")
    LOCALE_QUOTE_RE = re.compile(r'\$"[^"]*"')

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        block_network: bool = False,
        custom_blocked: list[str] | None = None,
        verbose: bool = True,
    ):
        super().__init__(workspace_root)
        self.verbose = verbose

        patterns = self.DEFAULT_BLOCKED_COMMANDS.copy()
        if block_network:
            patterns.extend(self.NETWORK_COMMANDS)
        if custom_blocked:
            patterns.extend(custom_blocked)

        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self.blocked_base_commands = set(self.DEFAULT_BLOCKED_BASE_COMMANDS)
        if block_network:
            self.blocked_base_commands.update(self.NETWORK_BASE_COMMANDS)

        if verbose:
            print(f"[DangerousCommands] Loaded {len(self.compiled_patterns)} blocked command patterns")

    @staticmethod
    def _unquoted_command(command: str) -> str:
        # @@@bash-hook-unquoted-scan - dangerous regexes should only inspect executable shell surface,
        # not literal text inside quotes.
        pieces: list[str] = []
        in_single = False
        in_double = False
        escaped = False

        for char in command:
            if escaped:
                if not in_single and not in_double:
                    pieces.append(char)
                escaped = False
                continue

            if char == "\\" and not in_single:
                if not in_double:
                    pieces.append(char)
                escaped = True
                continue

            if char == "'" and not in_double:
                in_single = not in_single
                continue

            if char == '"' and not in_single:
                in_double = not in_double
                continue

            if not in_single and not in_double and char == "#":
                prev = pieces[-1] if pieces else ""
                if not prev or prev.isspace():
                    break

            if not in_single and not in_double:
                pieces.append(char)

        return "".join(pieces)

    @classmethod
    def _has_dangerous_rm_flags(cls, tokens: list[str], start: int) -> bool:
        recursive = False
        force = False

        for token in tokens[start:]:
            if token in cls.OPERATOR_TOKENS:
                break
            if token == "--":
                break
            lowered = token.lower()
            if lowered == "--recursive":
                recursive = True
            elif lowered == "--force":
                force = True
            elif lowered.startswith("-"):
                short_flags = lowered[1:]
                recursive = recursive or "r" in short_flags
                force = force or "f" in short_flags
            if recursive and force:
                return True

        return False

    def _find_dangerous_command_word(self, command: str) -> str | None:
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
        except ValueError:
            return None
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = list(lexer)
        command_position = True

        for index, token in enumerate(tokens):
            if token in self.OPERATOR_TOKENS:
                command_position = True
                continue

            if token in {"<", ">", ">>", "<<", "<<<", "<>", ">|", "&>", "2>", "1>"}:
                command_position = False
                continue

            if not command_position:
                continue

            if self.ENV_ASSIGN_RE.match(token):
                continue

            if token in self.blocked_base_commands:
                return token

            if token == "rm" and self._has_dangerous_rm_flags(tokens, index + 1):
                return "rm -rf"

            command_position = False

        return None

    def check_command(self, command: str, context: dict[str, Any]) -> HookResult:
        stripped = command.strip()
        if self.ANSI_C_QUOTE_RE.search(stripped) or self.LOCALE_QUOTE_RE.search(stripped):
            return HookResult.block_command(
                error_message=(
                    f"❌ SECURITY ERROR: Dangerous command detected\n"
                    f"   Command: {command[:100]}\n"
                    f"   Reason: Obfuscated shell quoting is blocked for security reasons\n"
                    f"   Pattern: raw_obfuscation:$quote\n"
                    f"   💡 If you need to perform this operation, ask the user for permission."
                )
            )

        dangerous_word = self._find_dangerous_command_word(stripped)
        if dangerous_word is not None:
            return HookResult.block_command(
                error_message=(
                    f"❌ SECURITY ERROR: Dangerous command detected\n"
                    f"   Command: {command[:100]}\n"
                    f"   Reason: This command is blocked for security reasons\n"
                    f"   Pattern: command_word:{dangerous_word}\n"
                    f"   💡 If you need to perform this operation, ask the user for permission."
                )
            )

        scanned = self._unquoted_command(stripped)
        for pattern in self.compiled_patterns:
            if pattern.search(scanned):
                return HookResult.block_command(
                    error_message=(
                        f"❌ SECURITY ERROR: Dangerous command detected\n"
                        f"   Command: {command[:100]}\n"
                        f"   Reason: This command is blocked for security reasons\n"
                        f"   Pattern: {pattern.pattern}\n"
                        f"   💡 If you need to perform this operation, ask the user for permission."
                    )
                )
        return HookResult.allow_command()


__all__ = ["DangerousCommandsHook"]
