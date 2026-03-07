# Claude Code 工具调用校验层架构

> 基于黑盒实验（20+ 种错误场景）归纳，非官方文档。

---

## 整体流程

```
Claude 生成 tool_use
        ↓
  参数提取 & 反序列化
        ↓
  ┌─────────────────────────────┐
  │       校验层（统一入口）       │
  │  ┌─────────────────────┐   │
  │  │ Phase 1: 必需字段检查  │──→ 失败：简单文本格式
  │  ├─────────────────────┤   │
  │  │ Phase 2: 类型检查     │──→ 失败：简单文本格式
  │  ├─────────────────────┤   │
  │  │ Phase 3: 枚举/Union  │──→ 失败：JSON 数组格式
  │  │         结构校验      │   │
  │  └─────────────────────┘   │
  └─────────────────────────────┘
        ↓（通过）
    工具执行层
        ↓
  ┌─────────────────────────────┐
  │  成功 → 返回结果               │
  │  逻辑错误 → <tool_use_error>   │
  │  软性失败 → 普通文本            │
  └─────────────────────────────┘
```

---

## 校验层内部：两条代码路径

实验中发现**同为校验错误，但格式截然不同**：

```
# Phase 1 & 2 输出 → 简单文本
"Read failed due to the following issue:
The required parameter `file_path` is missing"

"The parameter `limit` type is expected as `number` but provided as `string`"

# Phase 3 输出 → JSON 数组
[
  {
    "code": "invalid_value",
    "values": ["content", "files_with_matches", "count"],
    "path": ["output_mode"],
    "message": "Invalid option: expected one of ..."
  }
]
```

这强烈暗示**两种不同的实现机制**：

- **Phase 1 & 2（命令式检查）**：手写的前置 if/else 校验，直接生成人类可读字符串，快速 fail，跳过后续 schema 解析。
- **Phase 3（声明式 schema 校验库）**：实际跑 JSON Schema 校验器，返回校验库原生的错误结构，error object 有固定字段：`code / values / path / message`。

Phase 3 的 error 结构特征：

| 字段 | 含义 |
|------|------|
| `code: "invalid_value"` | 枚举不匹配 |
| `code: "invalid_union"` | union 所有分支均失败，`errors` 嵌套每个分支的错误 |
| `path: ["param_name"]` | 指向出错的参数路径（支持嵌套） |
| `values: [...]` | 合法值列表，直接从 schema 读取 |

这个结构不像 Zod（Zod 用 `invalid_enum_value` + `options`），更像一个自研或轻量级的 schema 校验器。

---

## 什么被校验，什么没有

```
✅ 必需字段存在性（required）
✅ 基础类型匹配（string / number / boolean）
✅ 枚举值合法性（enum）
✅ Union 类型（anyOf / oneOf）

❌ 数值范围（minimum / maximum）
    → timeout: 999999999 超过 maximum:600000，照常执行
❌ 非枚举字符串格式约束
    → Grep type="invalid_type"，静默忽略
❌ additionalProperties 禁止额外字段
    → 推测，未直接测到
```

校验层**不是完整的 JSON Schema validator**，只实现了有限子集，聚焦于"能让工具正确执行"的约束。

---

## 错误包装：三层不同的返回形式

### 层级 1：InputValidationError（schema 校验失败）

```xml
<tool_use_error>InputValidationError: Read failed due to the following issue:
The required parameter `file_path` is missing</tool_use_error>
```

- 触发时机：进入工具执行前
- 特点：工具逻辑一行未跑

### 层级 2：执行错误（工具内部抛出异常）

```xml
<!-- 部分工具用 tool_use_error -->
<tool_use_error>String to replace not found in file.
String: some_string_xyz</tool_use_error>

<!-- 部分工具用 error -->
<error>File does not exist. Note: your current working directory is ...</error>
```

- 触发时机：工具运行时
- 特点：无 `InputValidationError` 前缀，**各工具格式不统一**（实现细节泄漏到接口层）

> ⚠️ **Leon**：在 Tool Runner 出口统一 normalize，handler 只管 throw，不负责包装格式。

### 层级 3：软性失败（逻辑上的"未命中"）

```
Task not found
No files found
```

- 触发时机：工具执行完毕，结果为空/未找到
- 特点：无任何包装标签，直接返回普通文本，需语义识别

> ⚠️ **Leon**：禁止将软性结果包进错误标签，会导致调用方误触重试。

---

## 推断的内部数据结构

```typescript
interface ToolDefinition {
  name: string;
  schema: JSONSchema;    // 参数声明，校验层使用
  handler: ToolHandler;  // 执行逻辑，校验通过后调用
}

type ValidationResult =
  | { ok: true; params: Record<string, unknown> }
  | { ok: false; error: string };  // 简单文本 or JSON.stringify(issues[])

type ExecutionResult =
  | { type: "success"; content: string }
  | { type: "tool_use_error"; message: string }
  | { type: "soft_failure"; message: string };  // 不包装，直接返回
```

---

## 实验数据：各错误场景汇总

原始数据见：`docs/CC/tool_schemas/error/error.json`

| 错误类型 | 触发方式 | 返回格式 |
|---------|---------|---------|
| 缺少单个必需参数 | `Read {}` | 简单文本 |
| 缺少多个必需参数 | `Write {}` | 简单文本，逐行列出 |
| 类型错误 string→number | `Read {limit: "abc"}` | 简单文本 |
| 类型错误 string→boolean | `Bash {run_in_background: "x"}` | 简单文本 |
| 枚举值非法（简单枚举） | `Grep {output_mode: "bad"}` | JSON 数组 |
| 枚举值非法（单值枚举） | `Agent {isolation: "bad"}` | JSON 数组 |
| union 类型非法 | `TaskUpdate {status: "bad"}` | JSON 数组，含 `invalid_union` |
| 文件不存在（Read） | 相对/不存在路径 | `<error>` 标签 |
| 文件不存在（Edit） | 不存在路径 | `<tool_use_error>` 标签 |
| 目录不存在（Glob） | 不存在 path | `<tool_use_error>` 标签 |
| Edit 字符串未找到 | old_string 不在文件中 | `<tool_use_error>` 标签 |
| Edit 多处匹配 | replace_all=false 但匹配 N 处 | `<tool_use_error>` 标签 |
| NotebookEdit 缺 cell_type | insert 模式未提供 cell_type | `<tool_use_error>` 标签（业务逻辑校验） |
| Task 不存在 | TaskGet/TaskUpdate 非法 ID | 普通文本 `Task not found` |
| 数值超出范围（未强制） | `Bash {timeout: 999999999}` | 正常执行，不报错 |
| 非枚举字符串非法（静默） | `Grep {type: "invalid_type"}` | 正常执行，`No files found` |

---

## 关键结论

| 问题 | 答案 |
|------|------|
| 校验层是否统一？ | **是**，所有工具共享同一套校验入口 |
| 两种错误格式的原因？ | 两条路径：命令式前置检查（简单文本）+ schema 库校验（JSON） |
| 是否完整实现 JSON Schema？ | **否**，仅校验必需字段、基础类型、枚举，数值范围等未强制 |
| 执行错误是否统一？ | **否**，各工具自行处理，`<tool_use_error>` vs `<error>` 均有出现 |
| 软性失败有 error 标签吗？ | **没有**，直接返回文本，需语义识别 |

## Leon 设计原则

层级间保留语义区分，**层级内必须统一**：

- 层级 1（参数错误）→ 调用方修正参数重试，需结构化
- 层级 2（执行错误）→ Tool Runner 出口统一包装，handler 只管 throw
- 层级 3（软性结果）→ 普通文本，禁止包错误标签
