# 移除 Worktree

清理并移除指定的 worktree。

## 参数

`$ARGUMENTS` = 分支名或目录名（如 `feat/eval`、`feat-eval`）。可省略，自动识别。

## Step 0：确定目标

优先级：命令参数 → 当前所在 worktree → 列出所有 worktree 询问用户

`<base-branch>` = 从对话上下文确定的项目默认开发分支。

```bash
MAIN_REPO=$(git worktree list | head -1 | awk '{print $1}')
PROJECT_NAME=$(basename "$MAIN_REPO")
```

- 当前目录是某个 worktree → 默认操作当前 worktree，确认后执行
- 当前目录是主仓库且无参数 → 列出所有 worktree，询问移除哪个
- 提供了参数 → 匹配分支名或目录名

worktree 可能在两个位置（兼容新旧路径）：
- 新路径：`~/worktrees/<项目名>--<目录名>`
- 旧路径：`$MAIN_REPO/worktrees/<目录名>`

用 `git worktree list` 获取实际路径，按分支名匹配即可。

## Step 1：检查未提交改动

```bash
git -C <worktree路径> status --short
```

有未提交改动 → 列出改动内容，询问用户：**继续移除（改动会丢失）？还是先处理？**

## Step 2：清理 untracked 文件

先移除已知的 symlink（`CLAUDE.local.md` 由 `wtnew` 创建，不在 Git 里）：

```bash
TARGET="<worktree路径>/CLAUDE.local.md"
[ -L "$TARGET" ] && rm "$TARGET" || echo "跳过：$TARGET 不是符号链接，不删除"
```

**必须用 `[ -L ]` 确认是 symlink 再删**，绝不对普通文件执行 `rm`，防止误删原始文件。

## Step 3：移除 worktree

```bash
git worktree remove "<worktree路径>"
```

如果仍然失败（`.venv`、`__pycache__` 等其他 untracked 文件残留）：

```bash
rm -rf "<worktree路径>"
git worktree prune
```

移除后，`config.worktree` 随 `.git/worktrees/<name>/` 自动清除，无需额外处理。

## Step 4：询问是否删除本地分支

先 fetch 远程 base 分支，确保合并判断基于最新状态：

```bash
git fetch origin <base-branch>
git branch -d <分支名>   # 基于最新 origin/<base-branch> 判断是否已合并
```

如果 `-d` 报"未合并"：用 `gh` 查该分支是否有已合并的 PR（squash/rebase merge 会改变 hash，`git branch -d` 检测不到）：

```bash
gh pr list --head <分支名> --state merged --json number,title --limit 1
```

- 返回非空（有已合并 PR）→ 安全删除 `git branch -D <分支名>`
- 返回空（无已合并 PR）→ 告知用户分支确实未合并，确认后再 `-D` 强删
- 不删除远程分支，除非用户明确要求
