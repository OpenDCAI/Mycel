# P2: Steps Tab 删除 + onFocusStep 链路清理

## Context

P1 完成后，ToolDetailBox 点击行为从 `onFocusStep`（跳 ComputerPanel Steps tab）改为打开 DetailBox Modal。Steps tab 的主要入口已不存在，tab 本身变成死功能。P2 清理这条死链路和关联的 Activities 系统。

**前置依赖**：P1（DetailBox Modal 替代 onFocusStep 作为 ToolDetailBox 的点击目标）

---

## 关键发现

### StepsView 需要拆分

`AgentsView.tsx` 复用了 `StepsView` 来渲染子 Agent 的工具流。不能直接删除 `StepsView.tsx`。

**方案**（按 Analysis）：提取 AgentsView 所需的渲染逻辑（`ToolFlowLine`、`TextFlowLine`、`StatusIcon` 等组件），移到 AgentsView 可直接引用的位置，然后删除 `StepsView.tsx`。

具体拆分：
- `ToolFlowLine`、`TextFlowLine`、`StatusIcon`、`getResultPreview` → 提取到 `computer-panel/flow-items.tsx`（AgentsView 复用）
- `ActivitySection`、`ActivityItem`、`ActivityStatusIcon`、`formatRelativeTime` → 随 StepsView 一起删除（死代码）
- `StepsView` 组件本身 → 删除

### Activities 只在 Steps tab 消费

`useActivities()` hook 产出的 `activities` 数据只传给 `StepsView` 的 `ActivitySection`。AgentsView 调用 StepsView 时不传 `activities`，所以 ActivitySection 不会在 Agents tab 中渲染。

**但**：P3 遗留的 `command_progress`/`background_task_*` 事件仍通过 `onActivityEvent` 路由到 `useActivities`。P2 删除 `useActivities` 后，这些事件需要一个新的去处，否则会被静默丢弃。

**方案**：P2 删除 `useActivities` 和 Activities UI，但在 `stream-event-handlers.ts` 中保留 `onActivityEvent` 回调接口（传 no-op 或 console.warn）。P3 统一 Background Task 时会重新设计这些事件的消费方式。

### tool-renderers 保留

`tool-renderers/` 通过 AgentsView → StepsView 仍在使用。P1 的 DetailBox Modal（P4 富渲染）也会复用。不删。

### extractMessageFlow / FlowItem 保留

`FlowItem` 类型被 AgentsView 和 `useSubagentStream` 使用。`extractMessageFlow` 从 `index.tsx` 移除调用即可，函数定义保留在 `utils.ts`。

---

## 实施步骤

### S1. ComputerPanel 移除 Steps tab

**`computer-panel/types.ts`**
- `TabType` 移除 `"steps"`：`"terminal" | "files" | "agents"`
- `ComputerPanelProps` 移除：`focusedStepId`、`onFocusStep`、`activities`、`onCancelCommand`、`onCancelTask`

**`computer-panel/TabBar.tsx`**
- `TABS` 数组移除 `{ key: "steps", label: "细节", icon: ListChecks }`
- 删除 `ListChecks` import

**`computer-panel/index.tsx`**
- 移除 `StepsView` import
- 移除 `extractMessageFlow` import 和 `flowItems` useMemo
- 移除 `activeTab === "steps"` 渲染块
- 移除 props 解构中的 `focusedStepId`、`onFocusStep`、`activities`、`onCancelCommand`、`onCancelTask`

### S2. onFocusStep 链路清理

**`hooks/use-app-actions.ts`**
- 移除 `focusedStepId` state
- 移除 `handleFocusStep` callback（含 `setComputerTab("steps")` + `setComputerOpen(true)` 逻辑）
- 从 `AppActionsState` 接口移除 `focusedStepId`、`setFocusedStepId`、`handleFocusStep`

**`pages/ChatPage.tsx`**
- 移除 `focusedStepId`、`setFocusedStepId`、`handleFocusStep` 解构
- 移除传给 ChatArea 的 `onFocusStep` prop
- 移除传给 ComputerPanel 的 `focusedStepId`、`onFocusStep` prop

**`components/chat-area/ChatArea.tsx`**
- 从 props 移除 `onFocusStep`
- 不再向下传递

**`components/chat-area/AssistantBlock.tsx`**
- 从 props 移除 `onFocusStep`
- `ContentPhaseBlock` 不再接收 `onFocusStep`

**`components/chat-area/ToolDetailBox.tsx`**
- 移除 `onFocusStep` prop（P1 已改为 Modal，此处只是清理残留）
- 确认 P1 的 Modal 点击行为正常工作

### S3. Activities 系统清理

**`hooks/use-activities.ts`**
- 删除整个文件

**`pages/ChatPage.tsx`**
- 移除 `useActivities()` 调用
- 移除 `activities`、`handleActivityEvent`、`cancelCommand`、`cancelTask` 解构
- 移除传给 ComputerPanel 的 `activities`、`onCancelCommand`、`onCancelTask` prop

**`hooks/use-stream-handler.ts`**（或 P1 重写后的等价文件）
- `onActivityEvent` 回调：改为 `console.warn`（`(e) => console.warn("[P3-pending] background event dropped:", e.type)`）
- 保留接口，P3 重新接入

### S4. StepsView 拆分

**现状**：AgentsView（line 140-146）将 `<StepsView flowItems={flowItems} activities={[]} focusedStepId={...} onFocusStep={...} autoScroll={...} />` 作为右侧详情面板渲染。StepsView 提供滚动容器（scrollRef + isAtBottomRef + auto-scroll useEffect）和 flowItems.map 渲染逻辑。

**新建 `computer-panel/flow-items.tsx`**
- 从 `StepsView.tsx` 提取：`ToolFlowLine`、`TextFlowLine`、`StatusIcon`、`getResultPreview`
- 额外提取：`FlowList` 组件 — StepsView 的滚动容器 + flowItems.map 渲染部分（约 30 行），去掉 `ActivitySection` 相关逻辑
- `FlowList` props：`{ flowItems, focusedStepId?, onFocusStep?, autoScroll? }`
- 保留对 `tool-renderers`、`chat-area/constants`、`chat-area/utils`、`MarkdownContent` 的 import

**修改 `computer-panel/AgentsView.tsx`**
- `import { StepsView } from './StepsView'` → `import { FlowList } from './flow-items'`
- line 140-146 的 `<StepsView ... />` → `<FlowList flowItems={flowItems} focusedStepId={agentFocusedStepId} onFocusStep={setAgentFocusedStepId} autoScroll={!!isRunning} />`
- 同时清理 AgentsView 自身的 `focusedStepId` / `onFocusStep` props（S2 已移除上游传递，AgentsView 不再从外部接收）
- AgentsView 保留内部的 `agentFocusedStepId` state（子 Agent 内部的 step 高亮）

**删除 `computer-panel/StepsView.tsx`**
- `StepsView` 组件本身、`ActivitySection`、`ActivityItem`、`ActivityStatusIcon`、`formatRelativeTime` 一并删除
- 滚动逻辑和渲染组件已迁移到 `flow-items.tsx`

---

## 轨道间依赖

```
P1 (DetailBox Modal) ──→ S2 (onFocusStep 清理)
                          │ P1 改了 ToolDetailBox 的 onClick，P2 只是删残留 prop
S1 (Steps tab) ── 独立
S3 (Activities) ── 独立（但保留 onActivityEvent 接口给 P3）
S4 (StepsView 内部) ── 可选
```

S1、S2、S3 可并行。S4 依赖 S1（先移除 Steps tab 对 StepsView 的引用，再拆分文件）。

---

## 关键文件清单

| 文件 | 改动 | 步骤 |
|------|------|------|
| `computer-panel/types.ts` | TabType 去 "steps"，Props 移除 5 个字段 | S1 |
| `computer-panel/TabBar.tsx` | TABS 数组移除 steps | S1 |
| `computer-panel/index.tsx` | 移除 StepsView 渲染块 + 相关计算 | S1 |
| `hooks/use-app-actions.ts` | 移除 focusedStepId + handleFocusStep | S2 |
| `pages/ChatPage.tsx` | 移除 onFocusStep/activities 传递链 | S2+S3 |
| `components/chat-area/ChatArea.tsx` | 移除 onFocusStep prop | S2 |
| `components/chat-area/AssistantBlock.tsx` | 移除 onFocusStep prop | S2 |
| `components/chat-area/ToolDetailBox.tsx` | 移除 onFocusStep prop 残留 | S2 |
| `hooks/use-activities.ts` | 删除文件 | S3 |
| `hooks/use-stream-handler.ts` | onActivityEvent 改为 no-op | S3 |
| `computer-panel/flow-items.tsx` | 新建：从 StepsView 提取核心渲染组件 | S4 |
| `computer-panel/AgentsView.tsx` | 改为从 flow-items 导入，替代 StepsView | S4 |
| `computer-panel/StepsView.tsx` | 删除 | S4 |

### 新建/删除的文件

| 文件 | 操作 |
|------|------|
| `computer-panel/flow-items.tsx` | **新建**：从 StepsView 提取的核心渲染组件 |
| `computer-panel/StepsView.tsx` | **删除**：拆分后不再需要 |
| `hooks/use-activities.ts` | **删除** |

### 不动的文件

| 文件 | 原因 |
|------|------|
| `components/tool-renderers/` | AgentsView → flow-items 仍用，P4 Modal 复用 |
| `computer-panel/utils.ts` | FlowItem/extractMessageFlow 被 AgentsView 使用 |

---

## 验证方案

1. **ComputerPanel 只剩 3 个 tab**：Terminal / Files / Agents，无 Steps
2. **ToolDetailBox 点击**：打开 DetailBox Modal（P1 行为），不切 tab
3. **Agents tab 正常**：选中 agent → 右侧 FlowList 渲染子 agent 工具流（来自 flow-items.tsx）
4. **无 console 报错**：确认没有引用不存在的 prop 或组件
5. **P3 遗留事件不崩溃**：`command_progress`/`background_task_*` 事件到达时不报错（被 no-op 吞掉）

## 不在 P2 范围

- Activities 重新设计展示位置 → P3
- tool-renderers 复用到 DetailBox Modal → P4
