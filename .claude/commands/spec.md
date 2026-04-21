# 更新 Mycel 架构规格

维护 `teams/specs/current/` 中的架构 ground truth。

## 参数

$ARGUMENTS = 可选的聚焦范围（如 `providers`、`sandbox lifecycle`、`commands`）。无参数则全量刷新。

## 写入边界

只能写 `teams/specs/current/*.md`。不能改代码、不能改其他目录。

## Hard Rules

1. 每条事实必须有 `path:line` 证据，否则标 `UNKNOWN`。
2. 代码 > 文档 > 日志 > 计划。冲突时以代码为准。
3. 完整覆写文件，不追加。
4. 不确定的事情直说，不猜。
5. 不写关于 spec 系统自身的内容——只写 Mycel 架构事实。
6. 幂等：如果现有内容已经准确反映代码事实，保持原文不动。不要为了重写而重写。
7. 自清理：覆写时自然淘汰过时事实。在汇报中说明删除了什么、为什么。

## 目标文件

```
teams/specs/current/
├── 00_scope.md      # 本次分析了什么、跳过了什么
├── 10_architecture.md   # 组件树 + 接线关系
├── 20_lifecycle.md      # session/terminal/lease 生命周期
├── 30_commands.md       # 命令执行流
├── 40_providers.md      # provider 能力矩阵
├── 50_data.md           # schema、状态、持久化
├── 60_tests.md          # 测试证据
└── 90_gaps.md           # 风险、矛盾、未知项
```

## 执行流程

### 1. 了解现状

读取 `teams/specs/current/` 所有文件，了解当前记录了什么。

### 2. 探索代码

自行决定需要读哪些源文件。核心入口点供参考：
- `agent.py` — agent 核心
- `sandbox/` — sandbox 系统
- `middleware/` — 中间件栈
- `core/command/` — 命令执行
- `backend/web/` — Web API
- `sandbox/providers/` — 各 provider 实现
- `tests/` — 相关测试

如果 $ARGUMENTS 指定了范围，聚焦该范围；否则全面扫描。

### 3. 覆写 current/*.md

对每个文件：读代码 → 提取事实（带 `path:line`）→ 覆写整个文件。

格式要求：
- 用 section 组织，不用全局编号列表
- 证据内联写在事实旁边
- `UNKNOWN` 必须说明原因
- 保持简洁，不写废话

### 4. 更新 00_scope.md

记录本次实际读了哪些文件、跳过了什么、为什么跳过。

### 5. 更新 90_gaps.md

记录发现的风险、代码与文档的矛盾、以及仍然未知的领域。

### 6. 汇报

简要说明：改了什么、发现了什么新事实、还有什么是 UNKNOWN。
