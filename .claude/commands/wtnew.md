# 创建 Worktree

基于最新 `origin/dev` 创建隔离的 worktree 开发环境，并自动拉起一个并行工作的 Kitty + Codex 开发位。

## 参数

`$ARGUMENTS` = 分支名（如 `feat/eval`、`yyh/fix-bug`）

## Step 0：定位主仓库

```bash
MAIN_REPO=$(git worktree list | head -1 | awk '{print $1}')
PROJECT_NAME=$(basename "$MAIN_REPO")
```

在主仓库或任意 worktree 下执行均可，自动找到主仓库根目录。

## Step 1：同步远端

```bash
git fetch origin
```

确保基于最新的 `origin/dev` 创建，避免从过时的 base 分叉。

## Step 2：启用 worktreeConfig

```bash
git config extensions.worktreeConfig true
```

幂等操作，已启用不报错。启用后每个 worktree 可拥有独立的 `config.worktree` 配置。

## Step 3：创建 worktree

目录名规则：分支名中的 `/` 替换为 `-`（如 `feat/eval` → `feat-eval`）

路径规则：`~/worktrees/<项目名>--<目录名>`（如 `~/worktrees/leon--feat-eval`）

```bash
git worktree add "$HOME/worktrees/$PROJECT_NAME--<目录名>" -b $ARGUMENTS origin/dev
```

- worktree 存放在 `~/worktrees/`，与主仓库完全隔离
- 确保 `~/worktrees/` 目录存在（`mkdir -p ~/worktrees`）

## Step 4：端口分配

为 worktree 分配独立的 backend + frontend 端口对，避免多 worktree 同时开发时端口冲突。

端口 8001/5173 保留给 main，worktree 从 offset=1 开始。

分配逻辑（**必须严格按以下脚本执行，不要自行简化，不要用 `&&` 把 while 和 for 串成一条命令**）：

```bash
# 用 git worktree list 获取所有 worktree 路径，逐个读取已声明端口
MAIN_REPO=$(git worktree list | head -1 | awk '{print $1}')
declared_ports=""
while read -r wt_path _rest; do
  [ "$wt_path" = "$MAIN_REPO" ] && continue
  bp=$(git -C "$wt_path" config --worktree --get worktree.ports.backend 2>/dev/null) || true
  fp=$(git -C "$wt_path" config --worktree --get worktree.ports.frontend 2>/dev/null) || true
  [ -n "$bp" ] && declared_ports="$declared_ports $bp"
  [ -n "$fp" ] && declared_ports="$declared_ports $fp"
  true  # 确保循环退出码为 0，避免 && 链断裂
done < <(git worktree list | tail -n +2)
echo "已声明端口: $declared_ports"

# 从 offset=1 开始找第一组未冲突的端口对
ASSIGNED_BACKEND=""
ASSIGNED_FRONTEND=""
for offset in $(seq 1 20); do
  bp=$((8001 + offset))
  fp=$((5173 + offset))
  # 检查 1：是否已被其他 worktree 声明
  if echo "$declared_ports" | grep -qw "$bp" || echo "$declared_ports" | grep -qw "$fp"; then
    echo "跳过 $bp/$fp（已声明）"
    continue
  fi
  # 检查 2：系统层是否占用
  if lsof -i :"$bp" >/dev/null 2>&1 || lsof -i :"$fp" >/dev/null 2>&1; then
    echo "跳过 $bp/$fp（端口占用）"
    continue
  fi
  ASSIGNED_BACKEND=$bp
  ASSIGNED_FRONTEND=$fp
  echo "✅ 分配: backend=$bp frontend=$fp"
  break
done

# 验证：确保没有分配 main 的端口
if [ "$ASSIGNED_BACKEND" = "8001" ] || [ "$ASSIGNED_FRONTEND" = "5173" ]; then
  echo "❌ 错误：不能将 main 的端口 (8001/5173) 分配给 worktree"
  exit 1
fi

# 验证：确保成功分配了端口
if [ -z "$ASSIGNED_BACKEND" ] || [ -z "$ASSIGNED_FRONTEND" ]; then
  echo "❌ 错误：未能找到可用端口对（已尝试 offset 1-20）"
  exit 1
fi
```

**重要**：执行此步骤后，必须在输出中看到：
- "已声明端口: ..." 行
- "✅ 分配: backend=xxxx frontend=xxxx" 行
- 分配的端口必须 >= 8002/5174（不能是 8001/5173）

## Step 5：写入 worktree config

```bash
cd "$HOME/worktrees/$PROJECT_NAME--<目录名>"
git config --worktree worktree.ports.backend $ASSIGNED_BACKEND
git config --worktree worktree.ports.frontend $ASSIGNED_FRONTEND
git config --worktree leon.backend.port $ASSIGNED_BACKEND
git config --worktree leon.frontend.port $ASSIGNED_FRONTEND
git config --worktree worktree.description "<AI 生成的描述>"
git config --worktree worktree.created "$(date +%Y-%m-%d)"
git config --worktree worktree.project "$PROJECT_NAME"

# 验证配置已正确写入
echo ""
echo "✅ 配置已写入："
git config --worktree --list | grep -E "(ports|leon\.(backend|frontend)\.port)"
```

description 由 AI 根据分支名和用户提供的上下文自动推断，简短描述这个分支的目的（中文，10-20 字）。

前后端代码会自动从 `git config --worktree` 读取端口，无需手动修改代码：
- `backend/web/main.py` → `_resolve_port()` 读取 `worktree.ports.backend`
- `frontend/app/vite.config.ts` → `getWorktreePort()` 读取 `worktree.ports.backend` 和 `worktree.ports.frontend`

**重要**：执行此步骤后，必须在输出中看到配置验证信息，确认端口已正确写入。

## Step 6：初始化开发环境

在 worktree 目录下创建独立的 Python 和 Node 环境：

```bash
cd "$HOME/worktrees/$PROJECT_NAME--<目录名>"

# Python：创建 .venv 并安装依赖
uv sync

# Node：安装前端依赖
cd frontend/app && npm install && cd ../..
```

两个命令都必须成功，失败时停下来排查，不要跳过。

## Step 7：链接本地配置

`.claude/` 已纳入 Git 管理，worktree checkout 后自动包含。
只需链接不在 Git 里的本地配置文件：

```bash
cd "$HOME/worktrees/$PROJECT_NAME--<目录名>"
ln -s "$MAIN_REPO/CLAUDE.local.md" CLAUDE.local.md 2>/dev/null
```

## Step 8：确认结果

输出：
- worktree 路径
- 分支名
- base 分支（必须明确是 `origin/dev`）
- 分配的端口（backend / frontend）
- 自动生成的描述
- `CLAUDE.local.md` 符号链接状态

## Step 9：自动拉起 Kitty + Codex 并行工作位

不要再询问“是否打开新的 Claude 会话”。默认直接拉起一个新的 Kitty tab，并在里面启动 Codex。

要求：
- tab title 固定为 `dev-feature`
- Codex 必须在新建好的 worktree 路径里启动
- 必须用实际计算出的完整绝对路径，不得保留变量或占位符
- 如果当前 shell 没有 `KITTY_LISTEN_ON`，要明确报错并停下，不要静默跳过

执行命令（**必须将路径替换为实际计算出的完整绝对路径，不得使用变量或占位符**）：

```bash
if [ -z "$KITTY_LISTEN_ON" ]; then
  echo "❌ 错误：未设置 KITTY_LISTEN_ON，无法自动创建 dev-feature kitty tab"
  exit 1
fi

kitty @ --to "$KITTY_LISTEN_ON" launch \
  --type tab \
  --tab-title "dev-feature" \
  --title "dev-feature" \
  zsh -lc 'cd "/Users/apple/worktrees/<项目名>--<目录名>" && codex --cd "/Users/apple/worktrees/<项目名>--<目录名>"'
```

关键：
- `cd` 和 `codex --cd ...` 必须写在新 tab 的命令字符串内部
- `codex --cd` 和前面的 `cd` 都必须指向同一个实际 worktree 绝对路径
- 不要退回 Terminal / osascript；这里的标准交互面就是 Kitty tab

## Step 10：最终输出

除了原有输出，再追加：
- `Codex tab: dev-feature`
- `Codex cwd: <worktree 绝对路径>`
- 如果启动成功，明确说明“并行开发位已就绪”
