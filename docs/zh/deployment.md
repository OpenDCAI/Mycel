# Mycel 部署指南

[English](../en/deployment.md) | 中文

## 前置要求

### 必需

- Python 3.11 或更高版本
- `uv` 包管理器（[安装指南](https://docs.astral.sh/uv/getting-started/installation/)）
- Git

### 可选（按 Provider）

- **Docker**：本地 Sandbox Provider 需要 Docker daemon
- **E2B**：从 [e2b.dev](https://e2b.dev) 获取 API key
- **Daytona**：从 [daytona.io](https://daytona.io) 获取 API key 或使用自托管实例
- **AgentBay**：API key 和区域访问权限

---

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/yourusername/leonai.git
cd leonai
```

### 2. 安装依赖

```bash
# 安装所有依赖，包括 Sandbox Provider
uv pip install -e ".[all]"

# 或仅安装特定 Provider
uv pip install -e ".[e2b]"      # 仅 E2B
uv pip install -e ".[daytona]"  # 仅 Daytona
uv pip install -e ".[sandbox]"  # 所有 Sandbox Provider
```

---

## 配置

### 用户配置目录

Mycel 将配置存储在 `~/.leon/`：

```
~/.leon/
├── config.json          # 主配置
├── config.env           # 环境变量
├── models.json          # LLM Provider 映射
├── sandboxes/           # Sandbox Provider 配置
│   ├── docker.json
│   ├── e2b.json
│   ├── daytona_saas.json
│   └── daytona_selfhost.json
└── leon.db              # SQLite 数据库
```

### 环境变量

创建 `~/.leon/config.env`：

```bash
# LLM Provider（OpenRouter 示例）
ANTHROPIC_API_KEY=your_openrouter_key
ANTHROPIC_BASE_URL=https://openrouter.ai/api/v1

# Sandbox Provider
E2B_API_KEY=your_e2b_key
DAYTONA_API_KEY=your_daytona_key
AGENTBAY_API_KEY=your_agentbay_key

# 可选：Supabase（如果使用远程存储）
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key
```

---

## Sandbox Provider 设置

### Local（默认）

无需配置。使用本地文件系统。

```bash
# 测试本地 Sandbox
leon --sandbox local
```

### Docker

**前置要求：** Docker daemon 运行中

创建 `~/.leon/sandboxes/docker.json`：

```json
{
  "provider": "docker",
  "on_exit": "destroy",
  "docker": {
    "image": "python:3.11-slim",
    "mount_path": "/workspace"
  }
}
```

**故障排除：**
- 如果 Docker CLI 卡住，检查代理环境变量
- Mycel 调用 Docker CLI 时会自动去除 `http_proxy`/`https_proxy`
- 使用 `docker_host` 配置覆盖 Docker socket 路径

### E2B

**前置要求：** E2B API key

创建 `~/.leon/sandboxes/e2b.json`：

```json
{
  "provider": "e2b",
  "on_exit": "pause",
  "e2b": {
    "api_key": "${E2B_API_KEY}",
    "template": "base",
    "cwd": "/home/user",
    "timeout": 300
  }
}
```

### Daytona SaaS

**前置要求：** Daytona 账户和 API key

创建 `~/.leon/sandboxes/daytona_saas.json`：

```json
{
  "provider": "daytona",
  "on_exit": "pause",
  "daytona": {
    "api_key": "${DAYTONA_API_KEY}",
    "api_url": "https://app.daytona.io/api",
    "target": "local",
    "cwd": "/home/daytona"
  }
}
```

### Daytona 自托管

**前置要求：** 自托管 Daytona 实例

**关键要求：** 自托管 Daytona 需要：
1. Runner 容器中有 bash（路径 `/usr/bin/bash`）
2. Workspace 镜像中有 bash（路径 `/usr/bin/bash`）
3. Runner 连接到 bridge 网络（以访问 Workspace 容器）
4. Daytona Proxy 在端口 4000 可访问（用于文件操作）

创建 `~/.leon/sandboxes/daytona_selfhost.json`：

```json
{
  "provider": "daytona",
  "on_exit": "pause",
  "daytona": {
    "api_key": "${DAYTONA_API_KEY}",
    "api_url": "http://localhost:3986/api",
    "target": "us",
    "cwd": "/workspace"
  }
}
```

**Docker Compose 配置：**

```yaml
services:
  daytona-runner:
    image: your-runner-image-with-bash
    environment:
      - RUNNER_DOMAIN=runner  # 不是 localhost！
    networks:
      - default
      - bridge  # 访问 Workspace 容器必需
    # ... 其他配置

networks:
  bridge:
    external: true
```

**网络配置：**

Runner 必须同时在 Compose 网络和 Workspace 容器所在的默认 bridge 网络上。在 Runner 的 `/etc/hosts` 中添加：

```
127.0.0.1 proxy.localhost
```

**故障排除：**
- "fork/exec /usr/bin/bash: no such file" → Workspace 镜像缺少 bash
- "Failed to create sandbox within 60s" → 网络隔离问题，检查 Runner 网络
- 文件操作失败 → Daytona Proxy（端口 4000）不可访问

### AgentBay

**前置要求：** AgentBay API key 和区域访问权限

创建 `~/.leon/sandboxes/agentbay.json`：

```json
{
  "provider": "agentbay",
  "on_exit": "pause",
  "agentbay": {
    "api_key": "${AGENTBAY_API_KEY}",
    "region_id": "ap-southeast-1",
    "context_path": "/home/wuying"
  }
}
```

---

## 验证

### 健康检查

```bash
# 检查 Mycel 安装
leon --version

# 列出可用 Sandbox
leonai sandbox ls

# 测试 Sandbox Provider
leon --sandbox docker
```

### 测试命令执行

```python
from sandbox import SandboxConfig, create_sandbox

config = SandboxConfig.load("docker")
sbx = create_sandbox(config)

# 创建会话
session = sbx.create_session()

# 执行命令
result = sbx.execute(session.session_id, "echo 'Hello from sandbox'")
print(result.output)

# 清理
sbx.destroy_session(session.session_id)
```

---

## 常见问题

### "Could not import module 'main'"

后端启动失败。检查：
- 是否在正确的目录下？
- 虚拟环境是否已激活？
- 使用完整路径运行 uvicorn：`.venv/bin/uvicorn`

### LLM 客户端报 "SOCKS proxy error"

Shell 环境设置了 `all_proxy=socks5://...`。启动前取消设置：

```bash
env -u ALL_PROXY -u all_proxy uvicorn main:app
```

### Docker Provider 卡住

Docker CLI 继承了代理环境变量。Mycel 会自动去除这些变量，但如果问题持续，检查 `docker_host` 配置。

### Daytona PTY 引导失败

检查：
1. Workspace 镜像在 `/usr/bin/bash` 有 bash
2. Runner 在 `/usr/bin/bash` 有 bash
3. Runner 在 bridge 网络上
4. Daytona Proxy（端口 4000）可访问

---

## 生产部署

### 数据库

Mycel 默认使用 SQLite（`~/.leon/leon.db`）。生产环境建议：

1. **定期备份：**
   ```bash
   cp ~/.leon/leon.db ~/.leon/leon.db.backup
   ```

2. **多用户部署考虑 PostgreSQL**（需要代码修改）

### 安全

- 将 API key 存储在 `~/.leon/config.env` 中，不要写在代码里
- 在配置文件中使用环境变量替换：`"${API_KEY}"`
- 限制文件权限：`chmod 600 ~/.leon/config.env`

### 监控

- 后端日志：检查 uvicorn 的 stdout/stderr
- Sandbox 日志：Provider 相关（Docker 日志、E2B 控制台等）
- 数据库：监控 `~/.leon/leon.db` 大小和查询性能

---

## 后续步骤

- 查看 [SANDBOX.md](../sandbox/SANDBOX.md) 了解详细的 Sandbox Provider 文档
- 查看 [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) 了解常见问题和解决方案
- 查看 `examples/sandboxes/` 中的示例配置
