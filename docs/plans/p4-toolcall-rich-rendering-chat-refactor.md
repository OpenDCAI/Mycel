# P4: ToolCall 富渲染

## Context

P1 创建了 DetailBox Modal（展开态），内容按时间序展示 Turn 完整执行细节，其中 ToolCall + ToolResult 采用两行紧凑格式。P2 删除了 StepsView（tool-renderers 的原主消费方，P2 后仅由 AgentsView 通过 flow-items.tsx 消费）。P3 建立了 Task Output API（子 Agent 详情数据源）。

P4 在 Modal 内实现 Spec 第四章的 ToolCall 富渲染：不同工具类型的结果有不同的渲染方式，不是千篇一律的纯文本。

**前置依赖**：P1（DetailBox Modal 已存在）、P2（StepsView 已删除，tool-renderers 需要新的消费方）、P3（Task Output API，子 Agent "查看详情"链接的数据源）

---

## 关键发现

### tool-renderers 现状

`tool-renderers/` 目录有 8 个 renderer + 1 个 registry，已覆盖所有 Spec 要求的工具类型。但：

1. **所有 expanded 视图都是 `<pre>` 纯文本**——无行号、无 diff、无结构化列表
2. **P2 删除 StepsView 后，这些 renderer 仅由 AgentsView（通过 flow-items.tsx）消费**——需要接入 P1 的 DetailBoxModal 作为主要消费方
3. **collapsed 视图是 renderer 自己的摘要行**——与 P1 两行紧凑格式（`getStepSummary`）存在重复

### 摘要行 vs 富渲染是两层

Spec 的 ToolCall 展示有两层：

1. **两行紧凑格式**（DetailBox 折叠态 + Modal 列表项）：`⏺ tool_name(key_arg)` + `⎿ Read 45 lines`。P1 C1 用 `getStepSummary` 生成。
2. **富渲染**（Modal 内 ToolCall 展开时）：代码编辑器、Diff、匹配列表等。这是 P4 的内容。

当前 `getStepSummary` 只看 args 不看 result，无法生成 `Read N lines`、`Found N matches`、`Added N, removed M` 等摘要。P4 需要增强摘要生成逻辑。

### renderer 接口需调整

当前 `ToolRendererProps = { step: ToolStep, expanded: boolean }`。P4 中：
- `expanded: false` → renderer 不再负责摘要行（由 Modal 统一渲染两行格式）
- `expanded: true` → renderer 渲染富内容

实际上 P4 只使用 expanded 模式。collapsed 模式保留但不再是主要入口。

### 不引入重型依赖

代码编辑器和 Diff 视图不需要 Monaco/CodeMirror 这种 400KB+ 的编辑器。只需要：
- 行号 + 语法高亮：用 CSS grid 显示行号 + `highlight.js`（或纯 CSS 自定义高亮）
- Diff 视图：纯前端字符串 diff（`diff` npm 包 ~10KB），渲染为 unified diff 格式

### Write vs Edit 的 renderer 分离

当前 `TOOL_RENDERERS` 中 Write 和 Edit 共用 `EditFileRenderer`。但 Spec 对两者的渲染不同：
- Write：`Wrote N lines` + 写入内容（代码编辑器风格，带行号）
- Edit：`Added N, removed M` + Diff 视图

P4 需要将 Write 拆出来用独立的 `WriteFileRenderer`（或在 `EditFileRenderer` 内按 tool name 分支）。

---

## 实施步骤

### S1. 摘要行增强（`getStepSummary` → `getStepResultSummary`）

**修改 `components/chat-area/utils.ts`**

新增 `getStepResultSummary(step: ToolStep): string | null`，从 `step.result` 中提取结构化摘要：

| 工具 | 逻辑 | 示例输出 |
|------|------|---------|
| Read/read_file | 计算 result 行数 | `Read 45 lines` |
| Write/write_file | 计算 result 行数（或从 args.content 计算写入行数） | `Wrote 120 lines` |
| Edit/edit_file | 从 args 计算：`old_string` 行数 = removed，`new_string` 行数 = added | `Added 5, removed 3` |
| Grep/Glob/search/find_files | 计算 result 非空行数 | `Found 12 matches` |
| Bash/run_command | result 首行（截断 60 字符）或 exit code | `All 42 tests passed` |
| WebFetch/WebSearch/web_search | 从 result 提取搜索概要（如有），否则 `完成` | `Done` |
| Task/TaskCreate/... | 从 result 截取前 60 字符 | `审查完毕，无问题` |

返回 `null` 表示尚无结果（工具仍在执行），调用方显示 loading 状态。

**修改 P1 的 DetailBoxModal 中 ToolCall 渲染**：
- 第二行从 `getStepSummary`（只看 args）改为优先用 `getStepResultSummary`（看 result），fallback 到 `getStepSummary`（看 args）

### S2. 共享基础组件

**新建 `components/tool-renderers/CodeBlock.tsx`**

行号 + 代码显示组件，替代所有 renderer 中的 `<pre>` 块：

```
props: {
  code: string
  startLine?: number        // 行号起始（默认 1）
  maxHeight?: number        // 超过则折叠，默认 300px
  language?: string         // 语法高亮语言（从文件扩展名推断）
  highlights?: number[]     // 高亮行号（搜索匹配、diff 变更行）
  linePrefix?: Map<number, "+" | "-">  // diff 行前缀
}
```

特性：
- CSS grid 两列：行号列（固定宽度，右对齐，灰色）+ 代码列（`overflow-x-auto`）
- 行号列不可选中（`user-select: none`）
- 超过 `maxHeight` 时显示渐隐遮罩 + "展开全部（N 行）"按钮
- 语法高亮：**第一版不做**，纯 `font-mono` 等宽显示。后续可接 `highlight.js` 或 `shiki`（lazy load）
- `linePrefix` 模式下：`+` 行绿色背景，`-` 行红色背景（用于 Diff）

**新建 `components/tool-renderers/DiffBlock.tsx`**

Unified diff 视图组件：

```
props: {
  oldText: string
  newText: string
  fileName?: string
  maxHeight?: number
}
```

- 使用 `diff` npm 包（`diffLines`）计算差异
- 渲染为 unified diff 格式：`- old line`（红色背景）/ `+ new line`（绿色背景）/ 无变化行（白色）
- 内部使用 `CodeBlock` 渲染，通过 `linePrefix` prop 传递 diff 标记
- 超过 `maxHeight` 时同样折叠

### S3. 各 renderer 升级

**`ReadFileRenderer.tsx`**
- expanded 视图：`<pre>` → `<CodeBlock code={result} language={inferLang(filePath)} />`
- 从 `file_path` 推断语言（`path.extname` → language map）

**`EditFileRenderer.tsx`** — 仅处理 Edit 工具
- expanded 视图：两个独立的红/绿块 → `<DiffBlock oldText={old_string} newText={new_string} fileName={file_path} />`
- result 仍显示在 DiffBlock 下方（如果有）

**新建 `WriteFileRenderer.tsx`** — 处理 Write 工具
- collapsed：`写入 {filename}`
- expanded：`<CodeBlock code={content || result} language={inferLang(filePath)} />`
- `content` 从 `step.args.content` 获取（Write 工具的写入内容）

**`SearchRenderer.tsx`**
- expanded 视图：`<pre>` → `<CodeBlock code={result} />`
- 匹配行高亮：解析 result 中 `filename:line:content` 格式，提取行号传给 `highlights` prop
- 第一版：仅用 CodeBlock 带行号显示。后续可解析为结构化文件分组列表

**`RunCommandRenderer.tsx`**
- expanded 视图：保持暗色 terminal 风格的命令行，output 部分改为可折叠：
  - `max-h-[200px]` 改为 `maxHeight` prop 控制，超过时显示"展开全部"按钮
  - 展开后显示完整输出，附带"折叠"按钮

**`WebRenderer.tsx`**
- expanded 视图：`<pre>` → `<CodeBlock code={result} />`
- 第一版：与当前差异不大，但有行号和折叠能力

**`TaskRenderer.tsx`**
- expanded 视图：保持现有 streaming 渲染
- 新增"查看详情"链接：点击后通过 P3 的 Task Output Stream（`streamTaskOutput(taskId)` → `/tasks/{task_id}/stream`）打开实时流式详情页
- P4 依赖 P3 已完成，Task Output Stream API 已可用，无需 interim 路径

**`ListDirRenderer.tsx`**
- expanded 视图：`<pre>` → `<CodeBlock code={result} />`

**`TOOL_RENDERERS` registry 更新**
- `Write` / `write_file` → `WriteFileRenderer`（从 `EditFileRenderer` 拆出）
- 其余不变

### S4. DetailBoxModal 接入 tool-renderers

**修改 P1 的 `DetailBoxModal.tsx`**

Modal 内 ToolCall 项从纯文本两行格式升级为可展开的富渲染：

- 默认：两行紧凑格式（`⏺ tool_name(key_arg)` + `⎿ result_summary`）
- 点击单个 ToolCall → 展开该 ToolCall 的富渲染（使用 `getToolRenderer(step)` 获取对应 renderer，传 `expanded={true}`）
- 再次点击 → 折叠回两行格式
- 展开/折叠是 per-ToolCall 的，不影响其他 ToolCall

实现：
- ToolCall 项加 `expanded` state（默认 false）
- `expanded=false`：渲染两行格式
- `expanded=true`：渲染两行格式 + renderer expanded 内容（在下方展开）
- 使用 `framer-motion` 或 CSS `max-height` transition 做展开动画（如果项目已有 framer-motion）

### S5. `diff` 依赖安装

```bash
cd frontend/app && npm install diff && npm install -D @types/diff
```

`diff` 包（~10KB gzipped）提供 `diffLines`、`diffWords` 等函数，用于 DiffBlock。

---

## 轨道间依赖

```
S1 (摘要增强) ── 独立（utils.ts 修改）
S2 (基础组件) ── 独立（新文件）
S3 (renderer 升级) ── 依赖 S2（CodeBlock/DiffBlock）+ S5（diff 包）
S4 (Modal 接入) ── 依赖 S3（renderer 已升级）+ P1 C1（Modal 已存在）
S5 (依赖安装) ── 独立，先行
```

**可并行**：S1 + S2 + S5
**顺序**：S5 → S2 → S3 → S4，S1 随时

---

## 关键文件清单

| 文件 | 改动 | 步骤 |
|------|------|------|
| `components/chat-area/utils.ts` | 新增 `getStepResultSummary` | S1 |
| `components/chat-area/DetailBoxModal.tsx` | 接入 tool-renderers，ToolCall 可展开 | S1+S4 |
| `components/tool-renderers/CodeBlock.tsx` | **新建**：行号 + 折叠的代码显示组件 | S2 |
| `components/tool-renderers/DiffBlock.tsx` | **新建**：unified diff 视图组件 | S2 |
| `components/tool-renderers/WriteFileRenderer.tsx` | **新建**：Write 工具的 CodeBlock 渲染 | S3 |
| `components/tool-renderers/ReadFileRenderer.tsx` | `<pre>` → `<CodeBlock>` | S3 |
| `components/tool-renderers/EditFileRenderer.tsx` | 两块红/绿 → `<DiffBlock>` | S3 |
| `components/tool-renderers/SearchRenderer.tsx` | `<pre>` → `<CodeBlock>` + 匹配高亮 | S3 |
| `components/tool-renderers/RunCommandRenderer.tsx` | output 可折叠 | S3 |
| `components/tool-renderers/WebRenderer.tsx` | `<pre>` → `<CodeBlock>` | S3 |
| `components/tool-renderers/TaskRenderer.tsx` | 新增"查看详情"链接 | S3 |
| `components/tool-renderers/ListDirRenderer.tsx` | `<pre>` → `<CodeBlock>` | S3 |
| `components/tool-renderers/index.ts` | Write → WriteFileRenderer | S3 |
| `components/tool-renderers/types.ts` | 不变（props 接口保持） | — |

### 新建/删除的文件

| 文件 | 操作 |
|------|------|
| `components/tool-renderers/CodeBlock.tsx` | **新建**：行号 + 语法高亮 + 折叠 |
| `components/tool-renderers/DiffBlock.tsx` | **新建**：unified diff 渲染 |
| `components/tool-renderers/WriteFileRenderer.tsx` | **新建**：Write 工具独立 renderer |

### 不动的文件

| 文件 | 原因 |
|------|------|
| `components/tool-renderers/DefaultRenderer.tsx` | 兜底 renderer，保持现状 |
| `components/chat-area/ToolDetailBox.tsx` | P1 已改为 Modal 入口，P4 不需要动 |
| `hooks/` | 不涉及 |
| 后端 | P4 纯前端改动，无后端变更 |

---

## 验证方案

1. **Read**：Modal 内展开 Read ToolCall → 带行号的代码显示，超长文件自动折叠
2. **Edit**：Modal 内展开 Edit ToolCall → unified diff 视图，`-` 红色 / `+` 绿色
3. **Write**：Modal 内展开 Write ToolCall → 带行号的代码显示（写入内容）
4. **Search/Grep**：Modal 内展开 → 带行号显示，匹配行高亮
5. **Bash**：Modal 内展开 → 暗色命令行 + 可折叠 output
6. **摘要行**：DetailBox 折叠态 + Modal 列表 → 显示 `Read 45 lines`、`Found 3 matches`、`Added 5, removed 3` 等
7. **展开/折叠**：Modal 内点击 ToolCall 展开富渲染，再次点击折叠
8. **Sub Agent**：TaskRenderer 展示"查看详情"链接，点击跳转（interim → Agents tab，P3 就绪后 → Task Output API）
9. **性能**：长文件（1000+ 行）的 CodeBlock 不卡顿（CSS grid + overflow，无虚拟滚动）
10. **bundle 影响**：`diff` 包 ~10KB gzipped，无其他新重型依赖

## 不在 P4 范围

- 语法高亮（`highlight.js` / `shiki` 集成）→ 后续增量
- 虚拟滚动（超大文件性能优化）→ 未来
- 搜索结果结构化文件分组（解析 `file:line:content` 为树形）→ 后续增量
- Web Search 结果卡片化（title + URL + snippet）→ 后续增量
- CodeBlock 内文本搜索（Ctrl+F 增强）→ 未来
