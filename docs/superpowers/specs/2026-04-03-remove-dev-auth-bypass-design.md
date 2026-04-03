# Remove Dev Auth Bypass Design

## Goal

彻底删除前后端 dev auth bypass，让 Mycel 本地开发和真实运行共享同一套身份契约。

## Decision

采用方案 A：

- 删除后端 `LEON_DEV_SKIP_AUTH`
- 删除前端 `VITE_DEV_SKIP_AUTH`
- `/api/auth/register` 与 `/api/auth/login` 永远走真实路径
- 开发便利不进入 runtime/request/auth code path
- 如需辅助，仅允许 repo 外或脚本级工具来做注册/登录初始化

## Why

当前 bypass 不是“方便开发”的轻量捷径，而是污染主契约：

- 后端可以把所有请求压成 `dev-user`
- 前端可以同时还以为自己在跑真实账号
- 结果就是聊天归属、thread 可见性、sender ownership、register/login caller contract 全都出现双真相

这种模式越修越脏，不值得保留。

## Scope

本次只做这几件事：

1. 删除前端 store 中的 bypass identity 分支
2. 删除后端 dependency/auth router 中的 bypass 分支
3. 删除围绕 bypass 的测试与文案
4. 补真实 auth 的最小回归
5. 提供不进入 runtime 的开发辅助入口
6. 同步 checkpoint 文档，明确 `nu-04` 从“握手修补”转为“bypass 删除”

## Non-Goals

- 不做新的 runtime auth mode handshake
- 不保留任何假 token / 假 user / 假 entity fallback
- 不为了测试便利在后端继续藏一个 dev-user 分支
- 不改动 chat/thread/member 的真实所有权模型

## Implementation Shape

### Backend

- `backend/web/core/dependencies.py`
  - 删除 `_DEV_SKIP_AUTH` / `_DEV_PAYLOAD` / `is_dev_skip_auth_enabled()`
  - `_extract_jwt_payload()` 永远要求 Bearer token
  - `get_current_user_id()` / `get_current_entity_id()` 只走真实 token 解析

- `backend/web/routers/auth.py`
  - 删除 dev-bypass 409 fail-loud 逻辑
  - register/login 直接调用真实 auth service

### Frontend

- `frontend/app/src/store/auth-store.ts`
  - 删除 `DEV_SKIP_AUTH`
  - 删除 `DEV_MOCK_USER`
  - 初始 token/user/entityId 永远为空
  - `401` 时统一 logout，不再分 bypass/non-bypass

### Tooling

- 增加一个不进 runtime 的开发辅助脚本
  - 例如 `scripts/dev/register_and_login.py`
  - 功能只是在本地对运行中的 backend 发 register/login，请求成功后打印 token / user / entity_id
  - 这类工具不参与请求路径决策，不改变身份模型

## Testing

- 后端 router 测试：register/login 正常走 auth service
- 前端 store 测试或最小 source-level verification：无 bypass 初始态
- live verification：
  - 启动 backend
  - register
  - login
  - create thread
  - send message

## Risk

唯一真实风险是测试/同事还在按旧 bypass 契约操作。

应对方式不是保留 bypass，而是：

- 提前通知测试侧
- 给一个显式 dev helper
- 用真实 auth 验证替代旧 bypass 流程
