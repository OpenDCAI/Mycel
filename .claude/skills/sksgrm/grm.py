#!/usr/bin/env python3
"""sksgrm - Delete an entire skill group."""

import shutil
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
        print(f"{GRAY}用法：/sksgrm <组名>{RESET}")
        sys.exit(1)

    group = sys.argv[1]
    _, skills_dir, groups_dir = get_paths()
    group_dir = groups_dir / group

    if not group_dir.exists():
        print(f"❌ 组 '{group}' 不存在")
        sys.exit(1)

    for skill_dir in group_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        link = skills_dir / skill_dir.name
        if link.is_symlink():
            link.unlink()
            print(f"  {GRAY}○ 关闭 {skill_dir.name}{RESET}")

    shutil.rmtree(group_dir)
    print(f"✅ 已删除组 {BOLD}{group}{RESET}\n")


if __name__ == "__main__":
    main()
