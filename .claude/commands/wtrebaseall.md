# 批量 Rebase 所有 Worktree

一个 PR 合并后，批量将所有 in-progress worktree rebase 到最新 `origin/<base-branch>`。

## 使用时机

某个分支的 PR 合并后（尤其是 rebase and merge），其他 worktree 的 base 已过时，统一更新。

## Step 0：定位主仓库

`<base-branch>` = 从对话上下文确定的项目默认开发分支。

```bash
MAIN_REPO=$(git worktree list | head -1 | awk '{print $1}')
```

在主仓库或任意 worktree 下执行均可。

## Step 1：同步远端

```bash
git fetch origin
```

## Step 2：遍历所有 worktree

对每个 worktree 逐一处理（跳过主仓库本身），无论在 `~/worktrees/` 还是旧路径 `$MAIN_REPO/worktrees/`：

```bash
git worktree list --porcelain
```

**跳过条件：**
- 当前 worktree 就是主仓库
- 对应分支的 PR 已 merged/closed（标记建议用 `wtrm` 清理）

**处理流程：**

```
DIRTY 检查
├── 有未提交改动 → 跳过，标记为"需手动处理"
└── 干净 → git -C <path> rebase origin/<base-branch>
         ├── 成功 → 标记 ✅
         └── 有冲突 → git -C <path> rebase --abort（回滚）
                      标记为"需手动处理"，继续下一个
```

冲突时自动 abort 而不是停下来等待，保证批量操作不会卡住。

## Step 3：汇总报告

```
wtrebaseall 完成
─────────────────────────────────────
✅ 成功 rebase：
  - ~/worktrees/leon--feat-x (feat/x)  +2 新 commit
  - ~/worktrees/leon--fix-y  (fix/y)   已是最新

⚠ 跳过（有未提交改动，需手动处理）：
  - ~/worktrees/leon--wip-z (wip/z)

❌ 冲突（已 abort，需手动处理）：
  - worktrees/old-a (old/a)
    提示：cd worktrees/old-a && git rebase origin/<base-branch>

🗑 建议清理（PR 已关闭）：
  - worktrees/done-b (done/b) → PR #9 merged
    执行：/wtrm done/b
─────────────────────────────────────
成功 2 / 跳过 1 / 冲突 1 / 待清理 1
```

报告中使用 `git worktree list` 返回的实际路径，兼容新旧两种位置。
