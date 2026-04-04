# Mycel Admin 管理后台

[English](../en/admin-panel.md) | 中文

Mycel Admin 是一个独立的内部管理面板，用于管理 Mycel 平台的成员和邀请码。

> **安全警告**：后端使用 Supabase service-role 密钥直连数据库，**绝不能暴露到公网**，只能通过 SSH 隧道或内网访问。

---

## 架构

```
mycel-admin/
├── backend/          # FastAPI 后端（Python）
│   ├── main.py       # 全部 API 路由
│   └── .env          # 环境变量（不入库）
└── src/              # React 前端（TypeScript + Vite）
    ├── api/client.ts # HTTP 客户端（封装 fetch）
    ├── store/        # Zustand 状态（workspace 切换）
    └── pages/        # 页面组件
```

**端口约定**

| 服务 | 端口 |
|------|------|
| 前端 (Vite dev) | 3100 |
| 后端 (FastAPI) | 3101 |

---

## Workspace 概念

后端维护两个 Supabase 客户端，分别对应不同 schema：

| Workspace | Schema |
|-----------|--------|
| `production` | `public` |
| `staging` | `staging` |

每个 API 请求通过 `X-Workspace` 请求头指定目标环境。前端 workspace 切换后，所有页面会自动重新拉取数据。

---

## 启动方式

### 前置条件

- Node.js + npm（前端）
- Python 3.11+ + `uv`（后端）

### 后端

```bash
cd mycel-admin/backend

# 创建 .env
cat > .env << EOF
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
EOF

# 安装依赖并启动
uv run uvicorn main:app --port 3101 --reload
```

### 前端

```bash
cd mycel-admin
npm install
npm run dev  # 访问 http://localhost:3100
```

---

## API 接口

所有接口通过 `X-Workspace: production | staging` 请求头切换目标环境。

### 邀请码

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/invite-codes` | 列出全部邀请码（按创建时间倒序） |
| POST | `/invite-codes` | 创建邀请码（`code` 和 `expires_days` 均可选） |
| DELETE | `/invite-codes/{code}` | 撤销邀请码 |

邀请码状态由后端计算：`available` / `used` / `expired`。

### 成员

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/members` | 列出全部成员 |
| PUT | `/members/{id}` | 更新成员（`name`、`is_admin` 字段可选） |
| DELETE | `/members/{id}` | 删除成员 |

---

## 功能

- **成员管理**：查看成员列表、切换管理员权限、删除成员
- **邀请码管理**：查看状态（有效/已使用/已过期）、生成新码、撤销已有码
- **Workspace 切换**：切换到预发环境时顶部显示黄色警告横幅，防止误操作

---

## 安全说明

- 后端使用用户名/密码认证，token 由 HMAC-SHA256 自签名
- `SUPABASE_SERVICE_ROLE_KEY` 绕过所有 RLS 策略，直接操作数据库
- 生产部署地址：`https://admin.mycel.nextmind.space`（通过 FRP + nginx 反代，HTTPS 在 aliyun 终止）
