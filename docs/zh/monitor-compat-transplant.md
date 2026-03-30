# Monitor 兼容版移植说明

## 变更背景

当前 `main` 分支上的 monitor 已退化为较早期的 sandbox console，仅保留：

- Threads
- Leases
- Diverged
- Events

而 `/home/dataset-local/data1/Mycel-compat-monitor-pr93` 中的 monitor 已扩展出：

- Evaluation 列表与详情
- Session 详情
- Thread Trace / Steps / Conversation
- 运行中评测线程的可视化展示

本分支的目标是将这套兼容版 monitor 能力移植回最新版 `main`，并补齐当前主线上的运行环境适配。

## 本次变更内容

### 1. 移植 monitor 前后端

移植并恢复了以下 monitor 能力：

- `EvaluationPage`
- `EvaluationDetailPage`
- `SessionDetailPage`
- `Thread Trace`
- `Conversation / Events / Steps` 多视图
- `/api/monitor/evaluations`
- `/api/monitor/evaluation/{evaluation_id}`
- `/api/monitor/evaluation/runs`
- `/api/monitor/session/{session_id}`
- `/api/monitor/thread/{thread_id}/trace`

对应文件：

- `backend/web/monitor.py`
- `backend/web/routers/monitor.py`
- `frontend/monitor/src/App.tsx`
- `frontend/monitor/src/styles.css`
- `frontend/monitor/vite.config.ts`

### 2. 适配最新版 main 的后端结构

为兼容当前主线的存储拆分与路由结构，补了以下适配：

- monitor router 改为桥接到 `backend.web.monitor`
- 保留主线已有的：
  - `/api/monitor/health`
  - `/api/monitor/resources`
  - `/api/monitor/resources/refresh`
  - `/api/monitor/sandbox/{lease_id}/browse`
  - `/api/monitor/sandbox/{lease_id}/read`
- run event 查询切换到 `SQLiteDBRole.RUN_EVENT`
- sandbox 会话查询继续走 `SQLiteDBRole.SANDBOX`
- evaluation 主数据继续走主库 `DB_PATH`

### 3. 修复 monitor 显示异常

修复了几个会导致“看起来不对劲”的问题：

- 兼容版 monitor 在最新版主线上被错误替换成旧版 console
- `Threads` 页此前只看 `chat_sessions`，运行中的 SWE-Bench 线程只写 checkpoint 时不会显示
- `Evaluation detail` 在没有 session、只有 checkpoint 的阶段不会渲染线程行
- conversation 视图之前直接请求 `/api/threads/{thread_id}`，会因为缺少 Bearer token 报：
  - `Conversation load failed: Missing or invalid Authorization header`
- 现在已改为走 monitor 专用的：
  - `/api/monitor/thread/{thread_id}/conversation`

### 4. 恢复 SWE-Bench 运行入口

当前主线 monitor UI 里保留了 SWE-Bench 入口，但执行脚本已经不在仓库中。为让 monitor 的 evaluation 功能可实际执行，本分支恢复了：

- `eval/swebench/run_slice.py`

并做了当前环境适配：

- 兼容 monitor 传入的 `--eval-timeout-sec`
- 兼容 monitor 传入的 `--git-timeout-sec`
- 允许从本地 `~/.leon/models.json` 读取 `OPENAI_API_KEY`
- trace DB 默认优先读取 `LEON_SANDBOX_DB_PATH`
- 在 trace DB 尚未生成时允许降级继续运行

### 5. 补齐评测依赖声明

将 monitor 的 SWE-Bench 运行依赖加入项目依赖声明：

- `datasets`
- `swebench`
- `socksio`

对应文件：

- `pyproject.toml`
- `uv.lock`

## 已验证内容

### 编译/构建验证

已完成：

- `python3 -m py_compile backend/web/monitor.py`
- `python3 -m py_compile backend/web/routers/monitor.py`
- `python3 -m py_compile eval/swebench/run_slice.py`
- `cd frontend/monitor && npm run build`

### 接口验证

已确认以下接口可用：

- `/api/monitor/evaluations`
- `/api/monitor/evaluation/{evaluation_id}`
- `/api/monitor/evaluation/runs`
- `/api/monitor/session/{session_id}`
- `/api/monitor/thread/{thread_id}/trace`
- `/api/monitor/thread/{thread_id}/conversation`
- `/api/monitor/resources`

### 运行态验证

已通过 monitor 发起 1 条最小 SWE-Bench 测试任务，并验证：

- 任务可在 evaluation 列表中显示
- 任务可在 Threads 页显示
- evaluation detail 可显示 checkpoint-only 线程
- conversation 接口不再因缺少 Authorization header 报错

## 当前分支说明

本分支为：

- `monitor-compat-transplant`

目的：

- 将兼容版 monitor 能力迁回当前最新版 `main`
- 让 monitor 中的 SWE-Bench evaluation 不再停留在“界面存在但无法执行”的状态

## 后续建议

建议后续继续拆两步：

1. 将 `backend/web/monitor.py` 中与 SWE-Bench runner 强绑定的逻辑进一步抽到独立 service，降低 monitor 文件体积。
2. 为 monitor 的 evaluation 流程补自动化测试，覆盖：
   - checkpoint-only 线程可见性
   - conversation 接口
   - evaluation list/detail 在运行中状态下的稳定性
