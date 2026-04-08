#!/usr/bin/env python3
"""sksrm - Remove a single skill from a group."""

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
    if len(sys.argv) < 2 or "/" not in sys.argv[1]:
        print(f"{GRAY}用法：/sksrm <组名/skill名>{RESET}")
        print(f"{GRAY}示例：/sksrm frontend/react-expert{RESET}")
        sys.exit(1)

    arg = sys.argv[1]
    group, skill = arg.split("/", 1)
    _, skills_dir, groups_dir = get_paths()
    skill_dir = groups_dir / group / skill

    if not skill_dir.exists():
        print(f"❌ 未找到 {arg}，运行 {CYAN}/sksls{RESET} 查看")
        sys.exit(1)

    link = skills_dir / skill
    if link.is_symlink():
        link.unlink()
        print(f"  {GRAY}○ 关闭 {skill}{RESET}")

    shutil.rmtree(skill_dir)
    print(f"✅ 已删除 {BOLD}{arg}{RESET}\n")


if __name__ == "__main__":
    main()
