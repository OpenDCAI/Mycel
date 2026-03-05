# Chat Area Refactor Spec

## 一、协议层：5 种消息壳

LangChain 消息体系下，Leon 使用 5 种消息类型：

**HumanMessage** 是一个"壳"，里面装两种东西：
- **UserMessage**：用户手动在输入框里打的内容，发给主 Agent。
- **Notification**：系统自动生成的通知，不是用户打的。复用 HumanMessage 的壳是因为 LangChain 的 graph 只接受 HumanMessage 作为外部输入，Notification 需要伪装成 HumanMessage 才能注入到 Agent 的消息流里。Notification 的 content 直接就是 XML 文本，前端通过 `metadata.source === "system"` 来区分它是 Notification 还是普通 UserMessage。

Notification 分三种：
- **TaskNotification**：某个 Task Agent 在后台执行完毕，推送结果给主 Agent。
- **CommandNotification**：后台运行的 shell 命令执行完毕。
- **UserNotification**：轻量通知，干扰性最小。

**AIMessage**：Agent 输出的文本。一轮 Agent Turn 里可能产生多条 AIMessage（被 tool call 打断后继续输出）。

**ToolCall**：Agent 决定调用某个工具，发出的请求（包含工具名和参数）。

**ToolResult**：工具执行完毕返回的结果（包含返回内容和 tool_call_id）。

这五种消息都可以包含多模态内容（文本、图片等）。

## 二、运行时结构：Response → Turn

**Response（一次完整响应）**：从用户发消息到 Agent 最终安静下来的整个过程。一个 Response 由一个或多个 Agent Turn 组成。

**Agent Turn（一轮）**：Agent 被激活一次、执行到停下来的完整周期。每轮 Turn 里，Agent 可能：
- 输出文本（AIMessage）
- 调用工具（ToolCall → ToolResult）
- 再输出文本
- 再调工具
- 最终输出一段文本后停下来

Turn 的结束不意味着 Response 的结束。后台可能有异步任务还在跑，它们完成后会发 Notification 回来，可能触发一个新的 Turn。

### Turn 的边界标记

**实时流（SSE）**：`run_start` 和 `run_done` 事件分别标记 Turn 的开始和结束。

**历史加载（API）**：后端给每条消息的 metadata 打 `run_id`，前端靠 `run_id` 分组重建 Turn 结构：
- 相同 `run_id` 的连续消息 = 一个 Turn
- 两个不同 `run_id` 之间的 `source: "system"` HumanMessage = Turn 间的 Notification 分割线

### Turn 内部的分层结构

一个 Turn 在渲染层由两部分组成：

**第一层**：DetailBox + 最终 AI text（主消息区可见）

**第二层（DetailBox 内部）**：按时间顺序包含三种内容：
1. **Text**：Agent 中间输出的思考文本（AIMessage）
2. **Tool**：工具调用请求（ToolCall）和返回结果（ToolResult）
3. **Notice**：Agent 运行期间收到的 Notification（未产生新 Turn 的）

### Notification 与 Turn 的关系

Notification 的起因是 run in background 的任务（Task Agent 或后台命令）执行完毕。但它不一定会产生新的 Turn，关键取决于主 Agent 当时的状态：

- **Agent 还在跑（running）**：Notification 归入当前这一轮 Turn，不形成 Turn 边界，主消息区不产生可见的分割线。但 Notification 不会凭空消失——它会被记录在当前 Turn 的 DetailBox 里，用户点开 Modal 查看详情时，能在时间线中看到"中间收到了一条 TaskNotification"。
- **Agent 已停（idle）**：Notification 注入后唤醒主 Agent，开启一个新的 Agent Turn。只有这种情况才形成 Turn 分割，在主消息区产生可见的 Notification 分割线。

多条 Notification 可以同时到达（比如三个 Task Agent 几乎同时完成），它们作为一批 HumanMessage 一起注入，触发一个新的 Turn。消息队列机制已在后端实现。

## 三、主消息区渲染逻辑

主消息区不是把所有 AIMessage / ToolCall / ToolResult 平铺展示的，而是有一套**分层披露**策略。

### 一个 Agent Turn 的渲染

一个 Turn 在主消息区的最终呈现由两部分组成：

**DetailBox（可选）**：如果这轮 Turn 有任何 tool call，就会生成一个 DetailBox。它是这个 Turn 的完整执行细节的折叠容器，用户不需要看到每一步的细节，只需要知道"这一轮做了什么"。点击可以展开 Modal 查看完整细节。

DetailBox 内部按时间顺序包含以下四种内容：
1. **AIMessage**：Agent 在工具调用之间输出的中间文本（思考过程），不在主消息区显示
2. **ToolCall**：工具调用请求（名称、参数）
3. **ToolResult**：工具调用返回结果
4. **Notification**：Agent 运行期间收到的通知（未产生新 Turn 的那些），主消息区不可见，仅在 DetailBox 中记录

**最终 AI text**：这轮 Turn 最后一条 AIMessage。这是 Agent 处理完所有工具调用后，给出的最终回答。

如果一轮 Turn 没有任何 tool call（纯文本回复），就没有 DetailBox，只有 AI text。

### 流式中的行为

当一轮 Turn 正在执行时：

0. Agent 第一个动作就是 tool call（没有任何文字）→ 主消息区为空，DetailBox 直接出现并开始更新
1. Agent 开始输出 AI text → 主消息区实时流式显示这段文字
2. Agent 决定调用工具 → 这段 AI text "沉"入 DetailBox，主消息区的文字消失（或被后续文字替换）
3. 工具执行完毕，Agent 继续输出新的 AI text → 主消息区显示这段新文字（替换/刷新，不是追加到之前的文字下面）
4. Agent 又调工具 → 又沉入 DetailBox
5. Agent 输出最终 AI text → 主消息区显示

关键行为：**主消息区永远只显示"最近"的那段 AI text**。前面被工具打断的中间文字都进了 DetailBox，不在主消息区堆叠。这样主消息区保持干净——用户看到的始终是 Agent 当前的思考/回答，而不是一大堆中间过程。

同时，DetailBox 在流式期间也在实时更新——新的工具调用会动态添加进去，结果返回后自动补上结果摘要行。

### 一轮结束后

当 Turn 结束（Agent 停止输出）：
- 最后一条 AI text 定格在主消息区
- DetailBox 收拢为摘要状态（显示工具数量、完成状态等）
- 这整个 Turn 的渲染固定不动

### 多轮的视觉排布

一个完整 Response 在主消息区的最终呈现（从上到下，按时间顺序）：

```
┌─ UserMessage ─────────────────────────────────┐
│  用户发的原始消息                                │
└───────────────────────────────────────────────┘

┌─ Turn 1 ──────────────────────────────────────┐
│  [DetailBox #1] 3 个工具调用 ✓              │
│  "根据分析结果，我建议..." (最终 AI text)        │
└───────────────────────────────────────────────┘

┌─ Notification ────────────────────────────────┐
│  ⚡ Task Agent "代码审查" 已完成                 │
│  ⚡ Task Agent "测试生成" 已完成                 │
└───────────────────────────────────────────────┘

┌─ Turn 2 ──────────────────────────────────────┐
│  [DetailBox #2] 2 个工具调用 ✓              │
│  "审查结果显示没有问题..." (最终 AI text)        │
└───────────────────────────────────────────────┘

┌─ Notification ────────────────────────────────┐
│  ⚡ 后台命令 "npm test" 已完成                   │
└───────────────────────────────────────────────┘

┌─ Turn 3（纯文本，无工具调用）──────────────────┐
│  "所有任务都已完成，总结如下..." (AI text)       │
└───────────────────────────────────────────────┘
```

Notification 出现在两个 Turn 之间的前提是 Turn 1 结束时 Agent 进入了 idle 状态，Notification 到达后才唤醒了 Turn 2。如果 Agent 还在跑的时候收到 Notification，主消息区不会出现分割线，Notification 被收入当前 Turn 的 DetailBox 中，用户可在 Modal 详情里查看。

每个已完成的 Turn 是静态的。只有当前正在执行的 Turn 是动态的（AI text 刷新、DetailBox 实时更新）。

## 四、DetailBox 交互

DetailBox 有三种视觉状态：

**静默态（Silent）**：Turn 执行完毕后的默认状态。高度约 3-4 行，显示摘要信息（工具数量、完成状态），无动效。

**执行态（Executing）**：Turn 正在执行时的状态。高度约 5-6 行，内容随工具调用实时流式更新，带动效。与静默态一样属于折叠状态——用户能看到概要（正在调用什么工具、哪个已完成），但看不到工具的完整参数和返回值。

**展开态（Expanded）**：用户点击 DetailBox 后弹出 Modal。Modal 按时间顺序展示这个 Turn 的完整执行细节：
- **AIMessage**：中间的思考文本
- **ToolCall + ToolResult**：工具调用的名称、参数、返回结果
- **Notification**：运行期间收到的通知（未产生新 Turn 的）
- **子 Agent ToolCall**：以 output 为主展示。有 output 则直接显示，无 output（仍在后台运行）则显示当前状态。均提供"查看详情"链接，跳转到子 Agent 的独立详情页（数据来自 Task Output API）。子 Agent 的执行过程不嵌套在父 Turn 的 DetailBox 里。

### ToolCall 的展示

DetailBox 内每个 ToolCall 采用两行紧凑格式，用内容本身反映状态，不加额外状态标签：

```
⏺ read_file("src/app.ts")
  ⎿  Read 45 lines

⏺ grep("TODO", "src/")
  ⎿  Found 3 matches

⏺ run_command("npm test")
  ⎿  All 42 tests passed

⏺ create_task("代码审查")
  ⎿  审查完毕，无问题         [查看详情]
```

第一行：工具名 + 关键参数。第二行：结果摘要。有结果 = 完成，无结果 = 还在跑，报错 = 直接显示错误信息。子 Agent 类型的 ToolCall 额外提供"查看详情"链接。

### ToolCall 的富渲染

不同工具类型的结果有不同的渲染方式，不是千篇一律的纯文本：

| 工具类型 | 摘要行 | 展开内容 |
|---|---|---|
| Bash | 直接展示输出，超过一屏自动折叠（可展开） | — |
| Search / Grep | `Found N matches` | 匹配结果列表 |
| Read | `Read N lines` | 文件内容（代码编辑器风格，带行号） |
| Write | `Wrote N lines` | 写入内容（代码编辑器风格，带行号） |
| Edit | `Added N, removed M` | Diff 视图（VS Code inline diff 风格，`-` 删除 / `+` 新增） |
| Web Search | `Did N search in Xs` | 搜索结果 |
| Sub Agent | 子 Agent 的 output | [查看详情] 跳转到独立详情页 |

不再跳转侧边面板。ComputerPanel 的 steps tab 删除。

## 五、SSE 事件协议收敛

### 现状

~20 种 SSE 事件，通过 type 前缀区分来源（`task_text`、`subagent_task_text`、`background_task_text`），本质是同一件事的重复。Task 和 SubAgent 语义完全重叠，唯一区别是 SubAgent 多一个 `parent_tool_call_id`。

### 收敛方案

把"是什么事"和"谁发的"分开。路由信息从 event type 移到 data payload：

```
// 现在
{ type: "subagent_task_tool_call", data: { task_id, parent_tool_call_id, ... } }

// 改后
{ type: "tool_call", data: { parent_tool_call_id: "tc_xyz", ... } }
```

收敛后事件类型（11 种）：

| 类型 | 事件 | 说明 |
|------|------|------|
| 内容 | `text` `tool_call` `tool_result` `error` `cancelled` | 5 种，靠 `parent_tool_call_id` 有无区分来源 |
| 生命周期 | `task_start` `task_done` `task_error` | 3 种，覆盖 Turn 内子 Agent 和 Background Task |
| 控制 | `status` `run_start` `run_done` | 3 种 |

原有的 `done` 事件删除——SSE 连接是持久的（跨 run 保持），不存在"整个 SSE 流结束"的概念。连接断开靠 SSE 本身的 close 事件感知。

原有的 `command_progress` 事件删除——Background Task 的状态和输出统一走 REST API（见第六章），SSE 只负责轻量的状态变化通知（`task_done`）。

### 事件路由

事件不携带 `agent_id`。Thread 是聊天主体，Agent 是幕后执行者——`agent_id` 是后端内部的生命周期管理概念，不泄漏到 SSE 协议层。

路由规则靠 `parent_tool_call_id` 这个关系字段：
- **无 `parent_tool_call_id`** → 主 Thread 事件，挂到当前 Turn
- **有 `parent_tool_call_id`** → 子 Agent 事件，挂到对应 ToolStep
- **有 `background: true` 且无 `parent_tool_call_id`** → Background Task 生命周期通知

~20 种 → 11 种。前端收到事件后，先看 `type` 决定怎么渲染，再看 `parent_tool_call_id` 决定往哪个 Turn / ToolStep 里挂。Background Task 的 `task_done` 只是触发前端 re-fetch Task Output API，不携带完整数据。

## 六、Background Task 与 Task Output

### 统一模型

两种后台运行的工作统一为 **Background Task**：

| 类型 | 触发方式 | 现在 | 统一后 |
|------|----------|------|--------|
| Background Bash | `run_command(background=true)` | `command_progress` SSE + `command_status` 工具 | Background Task |
| Background Task Agent | `create_task(...)` | `background_task_*` 系列 SSE 事件 | Background Task |

Background Bash 本质上也是一种 Task——它有 id、有状态、有输出，和 Task Agent 共享相同的生命周期。

### Task Output API

前端通过 REST API 获取 Background Task 的状态和输出，不依赖 SSE 推送：

```
GET /api/threads/:thread_id/tasks
→ [
    { task_id, type: "bash",  description: "npm test",  status: "running", started_at },
    { task_id, type: "agent", description: "代码审查",   status: "done",    started_at },
  ]

GET /api/threads/:thread_id/tasks/:task_id
→ { output: "...", exit_code: 0, ... }
```

前端拉取时机：
- 用户打开 Background Task 面板时 fetch
- 收到 `task_done` SSE 信号后 re-fetch
- 可选：定时轮询（执行态时）

### 与 SSE 的关系

SSE 不再推送 Background Task 的完整数据。`task_start` / `task_done` / `task_error` 事件只是轻量通知，告诉前端"有个后台任务状态变了，去 API 拉最新的"。

### 完成后的回注

Background Task 完成后，后端通过 Notification（HumanMessage 壳，`metadata.source = "system"`）将结果注入主 Agent 消息流。如果主 Agent 此时 idle，触发新的 Turn；如果 running，Notification 归入当前 Turn 的 DetailBox。

## 七、与当前实现的差距

| 方面 | 现在 | 改后 |
|------|------|------|
| AI text 展示 | 所有文字段按顺序堆叠在主消息区 | 主消息区只保留最近/最终的 AI text |
| 工具调用展示 | 作为 segments 和文字交替排列 | 收进 DetailBox，不在主消息区展开 |
| DetailBox 详情 | 跳侧边面板 steps tab | 弹 Modal |
| ComputerPanel steps tab | 存在 | 删除 |
| Agent Turn 边界 | 不明确，segments 混在一起 | 以 Notification 为分割（仅 Agent idle 时），每个 Turn 独立 |
| 流式中的 AI text | chunk 追加，所有文字可见 | 最近一条刷新覆盖，中间文字进 DetailBox |
| SSE 事件类型 | ~20 种，前缀区分来源 | 11 种，靠 parent_tool_call_id 路由 |
| Task/SubAgent | 两套平行事件 | 统一为一套，靠 parent_tool_call_id 有无区分 |
| Background Task | command_progress + background_task_* 两套 SSE 推送 | 统一为 Background Task，状态走 REST API，SSE 只发轻量通知 |

## 八、性能问题（顺带修复）

| 问题 | 位置 | 修复方式 |
|------|------|---------|
| `flushSync` 每个 text chunk 强刷 | `stream-event-handlers.ts` | 改为普通 setState，让 React 批处理 |
| 每次 chunk 重建 segments 数组 | `stream-event-handlers.ts` | 随协议重构一并优化 |
| MutationObserver 监听整棵子树字符变化 | `use-sticky-scroll.ts` | 移除 `characterData: true` |
| ComputerPanel 每次 SSE 事件重算 flowItems | `computer-panel/index.tsx` | 随 steps tab 删除一并清理 |

## 九、决策记录

- 前后端协议一起改（不做兼容过渡）
- DetailBox Modal 只展示当前 Turn 的工具调用（最小化）
- 虚拟滚动本次不做，留到下一轮
- ComputerPanel 的 steps tab 删除
- Notification 三种类型（Task / Command / User）保持不变，content 结构不同无法合并
- Background Task 的 UI 展示位置、取消入口——本次不设计，后续 UX 决策
- 子 Agent 在 DetailBox Modal 里以 output 为主，提供"查看详情"跳转到独立详情页，不在父 Turn 里嵌套子 Agent 的执行过程
- 主 Turn 的取消操作保持 InputBox stop 按钮

## 十、实施计划

- [可执行性分析](./chat-refactor-analysis.md)
- [P1: SSE 收敛 + 持久连接 + Chat 渲染重构 + DetailBox Modal](./plans/p1-sse-convergence-chat-refactor.md)
- [P2: Steps Tab 删除 + onFocusStep 链路清理](./plans/p2-steps-tab-cleanup-chat-refactor.md)
- [P3: Background Task 统一 + Task Output API](./plans/p3-background-task-unification-chat-refactor.md)
- [P4: ToolCall 富渲染](./plans/p4-toolcall-rich-rendering-chat-refactor.md)
- [P5: Agent 实例持久化 + SSE 事件清理](./plans/p5-agent-identity-and-event-cleanup.md)
