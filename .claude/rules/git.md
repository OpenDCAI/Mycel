# Git 规范

- Conventional Commits，小步提交，单一职责
- PR title/body 必须英文；push 前清理截图等 untracked 文件
- ❌ Push 必须用户授权，Claude 不能主动 push
- push 被拒 → `git rebase origin/<branch>`，❌ 不用 `reset --hard` / `pull --rebase`

## Worktree

统一放 `~/worktrees/<项目>--<feature>`，端口对写入 `git config --worktree`，用完 `git worktree remove` 清理。
