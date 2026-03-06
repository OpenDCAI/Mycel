#!/usr/bin/env python3
"""skssearch - Search SkillsMP for skills."""
import json
import os
import re
import sys
import subprocess
import threading
import urllib.parse
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


def load_api_key() -> str | None:
    """Load SKILLSMP_API_KEY from environment or shell config."""
    key = os.environ.get("SKILLSMP_API_KEY")
    if key:
        return key
    # Try to source shell configs
    for cfg in ["~/.zshrc", "~/.bash_profile", "~/.bashrc"]:
        result = subprocess.run(
            ["bash", "-c", f"source {cfg} 2>/dev/null; echo $SKILLSMP_API_KEY"],
            capture_output=True, text=True
        )
        key = result.stdout.strip()
        if key:
            return key
    return None


def fetch_url(url: str, api_key: str) -> dict:
    """Fetch JSON via curl."""
    result = subprocess.run(
        ["curl", "-s", "--max-time", "15", url, "-H", f"Authorization: Bearer {api_key}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def parse_install_cmd(github_url: str) -> str | None:
    """Derive install command from githubUrl."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/tree/[^/]+(/.+)", github_url)
    if not m:
        return None
    owner, repo, path = m.group(1), m.group(2), m.group(3).rstrip("/")
    skill_name = path.split("/")[-1]
    return f"{owner}/{repo}@{skill_name}"


def main() -> None:
    if len(sys.argv) < 2:
        print(f"{GRAY}用法：/skssearch <关键词>{RESET}")
        sys.exit(1)

    keyword = " ".join(sys.argv[1:])

    # Check for Chinese characters
    if re.search(r"[\u4e00-\u9fff]", keyword):
        print(f"❌ 检测到中文关键词，SkillsMP 仅支持英文搜索")
        print(f"建议使用英文关键词，例如：readme writer / documentation / testing")
        sys.exit(0)

    api_key = load_api_key()
    if not api_key:
        print("❌ 未找到 SKILLSMP_API_KEY")
        print("请设置环境变量并写入 shell 配置：")
        print("  echo 'export SKILLSMP_API_KEY=your_key' >> ~/.zshrc")
        sys.exit(1)

    enc = urllib.parse.quote(keyword)
    base = "https://skillsmp.com/api/v1/skills"
    results: dict[str, dict] = {}

    kw_data: list[dict] = []
    ai_data: list[dict] = []

    def fetch_kw():
        nonlocal kw_data
        data = fetch_url(f"{base}/search?q={enc}&limit=20&sortBy=stars", api_key)
        kw_data = data.get("data", {}).get("skills", []) if data.get("success") else []

    def fetch_ai():
        nonlocal ai_data
        data = fetch_url(f"{base}/ai-search?q={enc}", api_key)
        ai_data = data.get("data", {}).get("data", []) if data.get("success") else []

    t1 = threading.Thread(target=fetch_kw)
    t2 = threading.Thread(target=fetch_ai)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Merge results
    skills: dict[str, dict] = {}
    for s in kw_data:
        sid = s["id"]
        skills[sid] = {**s, "_from": "kw"}

    for item in ai_data:
        # AI search returns different structure: attributes.file contains skill metadata
        file_meta = item.get("attributes", {}).get("file", {})
        sid = file_meta.get("skill-id")
        if not sid:
            # Fallback to old structure
            s = item.get("skill", {})
            sid = s.get("id")

        if not sid:
            continue

        # Build skill dict from file metadata
        s = {
            "id": sid,
            "name": file_meta.get("skill-name", ""),
            "description": "",  # Not in file metadata, would need to parse content
            "githubUrl": "",    # Not available in this structure
            "stars": 0,         # Not available
            "author": sid.split("-")[0] if "-" in sid else "",  # Extract from ID
        }

        if sid not in skills:
            skills[sid] = {**s, "_from": "ai"}
        elif skills[sid]["_from"] == "kw":
            skills[sid]["_from"] = "both"

    if not kw_data and not ai_data:
        print(f"\n{GRAY}两路搜索均无结果，建议使用更通用的英文关键词。{RESET}\n")
        sys.exit(0)

    # Deduplicate by name, sort by stars
    by_name: dict[str, dict] = {}
    for s in skills.values():
        name = s.get("name", "")
        if name not in by_name:
            by_name[name] = s
        else:
            # Keep higher stars, but merge _from tags
            existing = by_name[name]
            if s.get("stars", 0) > existing.get("stars", 0):
                # Replace with higher-starred version, but preserve _from info
                s_from = s.get("_from", "kw")
                e_from = existing.get("_from", "kw")
                if s_from != e_from:
                    s["_from"] = "both"
                by_name[name] = s
            elif s.get("_from") != existing.get("_from"):
                # Same or lower stars, but different source - mark as both
                existing["_from"] = "both"
    result = sorted(by_name.values(), key=lambda x: -x.get("stars", 0))[:20]

    # Save for sksadd
    claude_dir, _, _ = get_paths()
    save = []
    for s in result:
        cmd = parse_install_cmd(s.get("githubUrl", "")) or s.get("name", "")
        save.append({**s, "installCmd": cmd})
    (claude_dir / ".sks-last-search.json").write_text(
        json.dumps(save, ensure_ascii=False, indent=2)
    )

    # Output
    print(f"\n{BOLD}搜索 \"{keyword}\" 共 {len(result)} 条：{RESET}\n")
    for i, s in enumerate(save, 1):
        name = s.get("name", "")
        desc = s.get("description", "").replace("\n", " ")
        stars = s.get("stars", 0)
        author = s.get("author", "")
        cmd = s.get("installCmd", "")
        src = s.get("_from", "kw")
        tag = (f"{GREEN}[kw+ai]{RESET}" if src == "both"
               else f"{CYAN}[ai]{RESET}" if src == "ai"
               else f"{GRAY}[kw]{RESET}")
        print(f"  {CYAN}{i:>2}. {BOLD}{name}{RESET}  {tag}  {GRAY}⭐{stars}  {author}{RESET}")
        if desc:
            print(f"      {GRAY}{desc[:80]}{'...' if len(desc) > 80 else ''}{RESET}")
        if cmd:
            print(f"      {GRAY}安装: npx skills add {cmd} --agent claude-code --copy -y{RESET}")
        print()

    print(f"{GRAY}运行 /sksadd <组名> <编号> 安装到指定组。{RESET}")
    print(f"{GRAY}如需先创建组，运行 /sksgnew <组名>。{RESET}\n")


if __name__ == "__main__":
    main()
