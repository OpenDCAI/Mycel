# Mycel Marketplace (mycel-hub) Architecture

## Overview

Marketplace 是 Mycel 的模块共享平台，允许用户发布、浏览、下载 Member/Agent/Skill/Env。

**双服务架构**：

```
Frontend (Vite)          Mycel Backend (FastAPI)          Mycel-Hub (FastAPI)          Supabase
+----------------+       +------------------------+       +---------------------+       +------------------+
| MarketplacePage| ----> | /api/marketplace/*     | ----> | /api/v1/*           | ----> | marketplace_*    |
| (read: direct) | ----> |  (write: publish/      |       | (port 8080)         |       | tables           |
|                |       |   download/upgrade)    |       |                     |       | supabase.f2j.space|
+----------------+       +------------------------+       +---------------------+       +------------------+
```

- **读操作**（浏览、搜索）：前端直连 Hub
- **写操作**（发布、下载、升级）：前端 -> Mycel Backend（权限校验 + 本地文件操作）-> Hub

## Mycel-Hub 服务 (`~/Mycel-Hub/`)

独立 FastAPI 服务，拥有所有 marketplace 数据，通过 Supabase Python SDK 操作数据库。

### 文件结构

```
~/Mycel-Hub/
  api/
    main.py              # FastAPI app, port 8080, CORS wildcard
    routes.py            # 所有 API 路由
  models/
    marketplace.py       # Pydantic 请求/响应模型
  services/
    marketplace_service.py  # Supabase CRUD 操作
  .env.example           # SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
  Dockerfile             # python:3.12-slim
  pyproject.toml         # deps: fastapi, uvicorn, supabase>=2.0.0
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/publishers/register` | Upsert publisher profile |
| GET | `/api/v1/items` | 列表/搜索 (type, q, sort, tags, publisher, page, page_size) |
| GET | `/api/v1/items/{id}` | 详情 + 最近 5 个版本 + parent |
| GET | `/api/v1/items/{id}/versions` | 所有版本 |
| GET | `/api/v1/items/{id}/versions/{version}` | 单个版本 + snapshot |
| GET | `/api/v1/items/{id}/lineage` | 祖先链 + 直接子项 |
| POST | `/api/v1/items/{id}/download` | 递增下载计数，返回 snapshot |
| POST | `/api/v1/publish` | 创建/更新 item + upsert version |
| POST | `/api/v1/check-updates` | 批量检查已安装项是否有新版本 |

### 环境变量

```
SUPABASE_URL=https://supabase.f2j.space
SUPABASE_SERVICE_ROLE_KEY=<service_role_key>
```

注意：使用 `service_role` key 直接操作，**无 RLS 策略**。

## Supabase Schema

三张表，部署在 `supabase.f2j.space`，**无 migration 文件**（通过 Dashboard 创建）。

### `marketplace_publishers`

| Column | Type | Note |
|--------|------|------|
| user_id | text PK | |
| username | text | |
| display_name | text | |
| bio | text | |
| avatar_url | text | |

### `marketplace_items`

| Column | Type | Note |
|--------|------|------|
| id | uuid PK | auto |
| slug | text | |
| type | text | member/agent/skill/env |
| name | text | |
| description | text | |
| publisher_user_id | text | |
| publisher_username | text | |
| parent_id | uuid | FK self-ref (fork 来源) |
| parent_version | text | |
| download_count | int | |
| visibility | text | |
| featured | bool | |
| tags | text[] | |
| search_vector | tsvector | FTS 用 |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Unique: `(type, publisher_user_id, slug)`

### `marketplace_versions`

| Column | Type | Note |
|--------|------|------|
| id | uuid PK | |
| item_id | uuid FK | -> marketplace_items |
| version | text | semver |
| release_notes | text | |
| snapshot | jsonb | 完整文件系统快照 |
| created_at | timestamptz | |

Unique: `(item_id, version)`

### Snapshot JSONB 结构 (member 类型)

由 Mycel Backend 的 `marketplace_client.py` 序列化：

```json
{
  "agent_md": "...",
  "rules": {"rule_name.md": "..."},
  "agents": {"agent_name.md": "..."},
  "skills": {"skill_name/SKILL.md": "..."},
  "mcp_json": {...},
  "runtime_json": {...}
}
```

## Mycel Backend 代理层

### 文件

```
backend/web/
  routers/marketplace.py       # /api/marketplace/* 路由
  services/marketplace_client.py  # Hub HTTP 客户端 + 本地文件读写
  models/marketplace.py        # 请求模型
  services/member_service.py   # publish_member(), install_from_snapshot()
```

### 代理路由 (`/api/marketplace`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/marketplace/publish` | 校验本地 member 所有权 -> Hub publish |
| POST | `/api/marketplace/download` | Hub download -> 写入本地 library |
| POST | `/api/marketplace/upgrade` | 校验所有权 -> Hub download -> 覆盖本地 |
| POST | `/api/marketplace/check-updates` | 转发到 Hub |

### 下载写入逻辑 (`marketplace_client.py`)

按 type 分发：
- **skill** -> `LIBRARY_DIR/skills/{slug}/SKILL.md` + `meta.json`
- **agent** -> `LIBRARY_DIR/agents/{slug}.md` + `{slug}.json`
- **member** -> `member_service.install_from_snapshot()` (创建完整目录结构)

安全：对 slug 做路径遍历校验。

### 环境变量

```
MYCEL_HUB_URL=http://localhost:8080  # Hub 地址
```

## Frontend

### 路由

```
/marketplace       -> MarketplacePage (Explore + Installed tabs)
/marketplace/:id   -> MarketplaceDetailPage
/library           -> redirect to /marketplace
```

### Store (`store/marketplace-store.ts`)

```
HUB_URL = VITE_MYCEL_HUB_URL || "http://localhost:8090"   # 直连 Hub (读)
API     = "/api/marketplace"                                # 代理 (写)
```

### 页面与组件

```
pages/
  MarketplacePage.tsx         # Explore tab (搜索/筛选/排序) + Installed tab (本地已安装)
  MarketplaceDetailPage.tsx   # 概览 (lineage) / 版本历史 / 文件预览

components/marketplace/
  MarketplaceCard.tsx         # 卡片 (类型 badge, 下载数, fork 标记)
  InstallDialog.tsx           # 下载确认弹窗
  UpdateDialog.tsx            # 升级弹窗 (版本 diff)
  LineageTree.tsx             # 祖先链 + 子项树
  PublishDialog.tsx           # 发布弹窗 (bump type, release notes, tags)
```

## 数据流

### 发布 (Publish)

```
PublishDialog -> appStore.publishMember(id, bump)     # 本地 meta.json 版本号 bump
             -> marketplaceStore.publishToMarketplace  # POST /api/marketplace/publish
             -> Mycel Backend: 校验 member 存在 + 序列化 snapshot
             -> Hub: POST /api/v1/publish              # upsert item + version
             -> Supabase: marketplace_items + marketplace_versions
```

### 下载 (Download)

```
InstallDialog -> marketplaceStore.download(id)         # POST /api/marketplace/download
              -> Mycel Backend: POST Hub /api/v1/items/{id}/download
              -> Hub: 递增 download_count, 返回 snapshot
              -> Mycel Backend: 按 type 写入本地文件, 写入 meta.json source 信息
```

### 检查更新

```
MarketplacePage Installed tab -> checkUpdates()
  -> POST /api/marketplace/check-updates
  -> Hub: 批量比较 installed_version vs latest version
  -> 返回有更新的 item 列表
```

## 测试

```
tests/test_marketplace_client.py   # download 文件写入、meta.json source 追踪、路径遍历防护
tests/test_marketplace_models.py   # Pydantic 模型校验
```

## 部署备注

- Hub 服务有 Dockerfile，运行在 port 8080
- Supabase 实例：`supabase.f2j.space`（自建，非 Supabase Cloud）
- 数据库 schema 手动创建，**无 migration 文件** -> 建议后续补充
- 无 RLS 策略，Hub 用 service_role key 直接操作 -> 安全性依赖 Hub 服务本身的鉴权
