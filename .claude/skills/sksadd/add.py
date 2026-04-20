#!/usr/bin/env python3
"""sksadd - Install skill from last search results into a group."""

import json
import re
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


def extract_error_reason(stdout: str, stderr: str) -> str:
    """Extract a concise failure reason from npx skills output."""
    combined = stdout + "\n" + stderr
    # Common patterns from npx skills output
    if "No matching skills found" in combined:
        m = re.search(r"No matching skills found for: (.+)", combined)
        return f"路径不存在：{m.group(1).strip()}" if m else "路径不存在"
    if "Could not find" in combined:
        return "找不到 skill（路径错误或仓库无此 skill）"
    if "ENOTFOUND" in combined or "ECONNREFUSED" in combined:
        return "网络连接失败"
    if "404" in combined:
        return "仓库或路径 404"
    if "already exists" in combined:
        return "skill 已存在（先删除再安装）"
    # Last resort: first non-empty stderr line
    for line in stderr.strip().splitlines():
        line = line.strip()
        if line and not line.startswith("npm"):
            return line[:120]
    return "未知错误（运行 npx skills add <cmd> 查看详情）"


def install_one(index: int, data: list, group: str, skills_dir: Path, group_dir: Path) -> bool:
    """Install a single skill. Returns True on success."""
    skill = data[index]
    install_cmd = skill.get("installCmd", "")
    skill_name = install_cmd.split("@")[-1].split("/")[-1] if "@" in install_cmd else install_cmd.split("/")[-1]

    print(f"{GRAY}[#{index + 1}] 正在安装 {skill_name}...{RESET}")

    if not install_cmd:
        print(f"{RED}[#{index + 1}] ❌ {skill_name} — 无安装命令（AI 搜索结果数据不完整）{RESET}")
        return False

    try:
        result = subprocess.run(
            ["npx", "skills", "add", install_cmd, "--agent", "claude-code", "--copy", "-y"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        print(f"{RED}[#{index + 1}] ❌ {skill_name} — 超时（30s）{RESET}")
        return False

    if result.returncode != 0:
        reason = extract_error_reason(result.stdout, result.stderr)
        print(f"{RED}[#{index + 1}] ❌ {skill_name} — {reason}{RESET}")
        return False

    installed = skills_dir / skill_name
    if not installed.exists():
        print(f"{RED}[#{index + 1}] ❌ {skill_name} — 安装后找不到文件（skill 名与目录名不匹配）{RESET}")
        return False

    dest = group_dir / skill_name
    shutil.move(str(installed), str(dest))
    print(f"[#{index + 1}] ✅ {BOLD}{skill_name}{RESET} → {group}")
    return True


def main() -> None:
    if len(sys.argv) < 3:
        print(f"{GRAY}用法：/sksadd <组名> <编号> [编号2 编号3 ...]{RESET}")
        print(f"{GRAY}先运行 {RESET}{CYAN}/skssearch <关键词>{RESET}{GRAY} 获取编号。{RESET}")
        sys.exit(1)

    group = sys.argv[1]
    try:
        indices = [int(x) - 1 for x in sys.argv[2:]]
    except ValueError:
        print("❌ 编号必须是整数")
        sys.exit(1)

    claude_dir, skills_dir, groups_dir = get_paths()
    last_search = claude_dir / ".sks-last-search.json"

    if not last_search.exists():
        print(f"❌ 没有搜索记录，请先运行 {CYAN}/skssearch <关键词>{RESET}")
        sys.exit(1)

    group_dir = groups_dir / group
    if not group_dir.exists():
        print(f"❌ 组 '{group}' 不存在，先运行 {CYAN}/sksgnew {group}{RESET}")
        sys.exit(1)

    data = json.loads(last_search.read_text())
    for i in indices:
        if i < 0 or i >= len(data):
            print(f"❌ 编号 {i + 1} 超出范围（共 {len(data)} 条结果）")
            sys.exit(1)

    results = [None] * len(indices)

    # npx skills 有全局锁，不支持并行，只能顺序安装
    for pos, idx in enumerate(indices):
        results[pos] = install_one(idx, data, group, skills_dir, group_dir)

    success = sum(1 for r in results if r)
    total = len(indices)

    if total > 1:
        print(f"\n{BOLD}安装完成：{success}/{total} 成功{RESET}")

    if success > 0:
        print(f"{GRAY}激活请运行：{RESET}{CYAN}/skson {group}{RESET}")
        print(f"\n{BOLD}⚠️  新安装的 skill 需要重启 session 才能生效{RESET}")
        print(f"{GRAY}请关闭当前 Claude Code 会话，重新打开后再运行 /skson {group}{RESET}\n")

    if success < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
