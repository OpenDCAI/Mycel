#!/usr/bin/env python3
"""skson - Activate all skills in a group."""
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
    if len(sys.argv) < 2:
        print(f"{GRAY}用法：/skson <组名>{RESET}")
        sys.exit(1)

    group = sys.argv[1]
    _, skills_dir, groups_dir = get_paths()
    group_dir = groups_dir / group

    if not group_dir.exists():
        print(f"❌ 组 '{group}' 不存在，运行 /sksls 查看所有组")
        sys.exit(1)

    skills_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for skill_dir in sorted(group_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        link = skills_dir / skill_dir.name
        if link.is_symlink():
            print(f"  {GRAY}跳过 {skill_dir.name}（已激活）{RESET}")
        else:
            link.symlink_to(skill_dir.resolve())
            print(f"  ✅ {GREEN}{skill_dir.name}{RESET}")
            count += 1

    print(f"\n{BOLD}已激活 {count} 个 skill{RESET}{GRAY}（组: {group}）{RESET}\n")


if __name__ == "__main__":
    main()
