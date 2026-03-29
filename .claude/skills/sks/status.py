#!/usr/bin/env python3
"""sks - Show active skills status and available commands."""
import sys
import os
import subprocess
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


def header(title: str) -> None:
    line = "─" * 40
    print(f"\n{BOLD}{title}{RESET} {GRAY}{line}{RESET}")


def main() -> None:
    claude_dir, skills_dir, groups_dir = get_paths()

    # Commands list
    print(f"{BOLD}可用命令{RESET}")
    cmds = [
        ("/sks",               "显示已激活 skill 和分组概览"),
        ("/sksls",             "列出所有组和 skill 的激活状态"),
        ("/skssearch <词>",    "搜索 SkillsMP（关键词 + AI 语义混合）"),
        ("/sksadd <组> <N>",   "从搜索结果安装第 N 条到指定组"),
        ("/skson <组>",        "激活整组"),
        ("/sksoff <组>",       "关闭整组"),
        ("/sksgnew <组>",      "创建新分组"),
        ("/sksgrm <组>",       "删除整组"),
        ("/sksrm <组/skill>",  "删除单个 skill"),
    ]
    for cmd, desc in cmds:
        print(f"  {CYAN}{cmd:<20}{RESET} {desc}")

    # Active skills
    header("已激活的 Skills")
    found = 0
    if skills_dir.exists():
        for item in sorted(skills_dir.iterdir()):
            if item.is_symlink():
                target = item.resolve()
                group = target.parent.name
                print(f"  ✅ {GREEN}{item.name}{RESET}  {GRAY}← {group}{RESET}")
                found += 1
    if found == 0:
        print(f"  {GRAY}（无激活的分组 skill）{RESET}")

    # Groups overview
    header("分组库")
    if groups_dir.exists() and any(groups_dir.iterdir()):
        for group_dir in sorted(groups_dir.iterdir()):
            if not group_dir.is_dir():
                continue
            gname = group_dir.name
            total = sum(1 for d in group_dir.iterdir() if d.is_dir())
            active = sum(
                1 for link in skills_dir.iterdir()
                if link.is_symlink() and gname in str(link.resolve())
            ) if skills_dir.exists() else 0
            print(f"  📁 {BOLD}{gname}{RESET}  {GREEN}{active}{RESET}{GRAY}/{total} 已激活{RESET}")
    else:
        print(f"  {GRAY}（暂无分组，运行 /sksgnew <组名> 创建）{RESET}")

    print()


if __name__ == "__main__":
    main()
