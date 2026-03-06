#!/usr/bin/env python3
"""sksls - List all skill groups and their activation status."""
import os
import subprocess
import sys
from pathlib import Path

# ANSI colors
BOLD  = "\033[1m"
CYAN  = "\033[36m"
GREEN = "\033[32m"
GRAY  = "\033[90m"
RED   = "\033[31m"
RESET = "\033[0m"


def get_paths() -> tuple[Path, Path, Path]:
    """Return (claude_dir, skills_dir, groups_dir)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        claude_dir = Path(result.stdout.strip()) / ".claude"
    except subprocess.CalledProcessError:
        claude_dir = Path.cwd() / ".claude"
    return claude_dir, claude_dir / "skills", claude_dir / "skill-groups"


def main() -> None:
    _, skills_dir, groups_dir = get_paths()

    if not groups_dir.exists() or not any(groups_dir.iterdir()):
        print(f"{GRAY}暂无分组，运行 /sksgnew <组名> 创建第一个组。{RESET}")
        sys.exit(0)

    for group_dir in sorted(groups_dir.iterdir()):
        if not group_dir.is_dir():
            continue
        print(f"\n📁 {BOLD}{group_dir.name}{RESET}")
        for skill_dir in sorted(group_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            link = skills_dir / skill_dir.name
            if link.is_symlink():
                print(f"  ✅ {GREEN}{skill_dir.name}{RESET}")
            else:
                print(f"  {GRAY}○  {skill_dir.name}{RESET}")

    print()


if __name__ == "__main__":
    main()
