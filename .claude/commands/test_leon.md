# 测试 Mycel 新功能

在开发 Mycel 时，用此命令验证新功能是否正常工作。

**重要**：Middleware 级别的更新必须通过此测试才能交付。

## 使用方法

```bash
/test-leon                    # Middleware 级别更新，执行完整测试
/test-leon <测试场景描述>      # 指定测试场景
```

## 何时必须执行

以下情况**必须**执行完整测试后才能交付：

- 新增或修改 `middleware/` 下的模块
- 修改 `agent.py` 核心逻辑
- 修改 `tui/app.py` 或 `tui/runner.py`
- 新增工具或修改工具行为
- 修改 checkpointer / session 相关逻辑

## 执行流程

### 1. 清理环境

测试前先清理可能卡住的进程：

```bash
# 杀掉 CLI 相关进程
pkill -9 -f "leonai" 2>/dev/null || true
pkill -9 -f "context7\|upstash" 2>/dev/null || true
sleep 1
```

### 2. 重新安装

每次测试前**必须**按以下顺序执行，确保测试的是最新代码：

```bash
# 1. 清除缓存（必须！否则可能安装旧版本）
# 如果提示 "Cache is currently in-use"，加 --force
uv cache clean mycel --force

# 2. 强制重新安装（必须用 --force）
uv tool install . --force
```

⚠️ 注意：
- `uv cache clean` 必须加 `--force`，否则可能因为有进程占用而卡住
- `uv tool install` 必须加 `--force`，否则不会覆盖已安装版本

### 3. 基础回归测试

无参数调用时，先执行基础回归，确保没有破坏已有功能：

#### 3.1 基础响应测试

```bash
leonai run -d "你好，用一句话介绍你自己"
```

验证：Agent 能正常响应，无报错。

#### 3.2 工具调用测试

```bash
leonai run -d "列出当前目录的文件"
```

验证：`[TOOL_CALL] list_dir` 出现，`[TOOL_RESULT]` 返回文件列表。

#### 3.3 命令执行测试

```bash
leonai run -d '用 run_command 执行: echo "hello"'
```

验证：`[TOOL_CALL] run_command` 出现，`[TOOL_RESULT]` 返回 `hello`，无 `[ERROR]`。

#### 3.4 多轮对话测试

```bash
cat << 'EOF' | leonai run --stdin -d
你好

列出当前目录的 Python 文件

读取 agent.py 的前 5 行
EOF
```

验证：3 轮对话都正常完成，工具调用正确。

#### 3.5 Thread 持久化测试

```bash
leonai run --thread test-mem-$(date +%s) "记住数字 42"
# 记录上面的 thread id，然后：
leonai run --thread <同一个thread-id> "我让你记住的数字是多少？"
```

验证：第二轮能正确回忆出 42。

### 4. 变更针对性测试（核心步骤）

基础回归通过后，**必须**针对本次变更设计并执行场景测试。

#### 4.1 分析变更

```bash
git diff HEAD          # 查看未提交的变更
git diff HEAD~1 HEAD   # 或查看最近一次提交
```

阅读 diff，理解本次改了什么功能、影响哪些工具/行为。

#### 4.2 设计测试场景

根据变更内容，构造能**触发变更路径**的测试用例。原则：

- 每个新增/修改的行为至少一个正向测试（验证功能生效）
- 关键的错误路径也要覆盖（验证错误提示正确）
- 测试应能通过 `leonai run` 的输出直接验证结果

#### 4.3 执行测试

**单轮快速验证**：

```bash
leonai run -d "<测试消息>"
```

**多轮验证**（stdin）：

```bash
cat << 'EOF' | leonai run --stdin -d --thread test-$(date +%s)
<第一轮消息>

<第二轮消息>
EOF
```

**持久化验证**（跨命令）：

```bash
leonai run --thread <thread-id> "<第一轮>"
leonai run --thread <thread-id> "<第二轮验证>"
```

**交互模式**（需要手动输入，如测试 Queue Mode）：

```bash
leonai run -i -d
```

#### 4.4 用户指定场景

如果用户通过 `/test-leon <场景描述>` 指定了测试场景，优先测试该场景，基础回归可酌情精简。

### 5. 结果分析

检查 debug 输出：
- `[TOOL_CALL]` - 工具是否被正确调用
- `[TOOL_RESULT]` - 工具返回是否正确
- `[QUEUE]` - 队列状态是否符合预期
- `[ASSISTANT]` - AI 响应是否合理
- `[SUMMARY]` - 总轮次和工具调用数

## 测试通过标准

- 基础回归：所有测试无报错，工具调用符合预期，多轮上下文正确，Thread 持久化正常
- 变更测试：本次变更的新功能/修复已被验证，正向和错误路径均符合预期
