#!/usr/bin/env python3
"""sksgnew - Create a new skill group."""

import subprocess
import sys
from pathlib import Path

# ANSI colors
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
GRAY = "\033[90m"
RED = "\033[31m"
RESET = "\033[0m"


def get_paths() -> tuple[Path, Path, Path]:
    """Return (claude_dir, skills_dir, groups_dir)."""
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        claude_dir = Path(result.stdout.strip()) / ".claude"
    except subprocess.CalledProcessError:
        claude_dir = Path.cwd() / ".claude"
    return claude_dir, claude_dir / "skills", claude_dir / "skill-groups"


def main() -> None:
    if len(sys.argv) < 2:
        print(f"{GRAY}用法：/sksgnew <组名>{RESET}")
        sys.exit(1)

    group = sys.argv[1]
    _, _, groups_dir = get_paths()
    group_dir = groups_dir / group

    if group_dir.exists():
        print(f"⚠️  组 {BOLD}{group}{RESET} 已存在")
        sys.exit(0)

    group_dir.mkdir(parents=True)
    print(f"✅ 已创建组 {BOLD}{group}{RESET}")
    print(f"{GRAY}搜索 skill：{RESET}{CYAN}/skssearch <关键词>{RESET}{GRAY}，然后运行 {RESET}{CYAN}/sksadd {group} <编号>{RESET}\n")


if __name__ == "__main__":
    main()
