# LAN Manual QA Deployment

目标：把 `leonai` PR 环境以固定方式启动，供同一局域网设备（如 Mac mini）直接手动试用。

## 标准流程（Jarvis 风格）

- 单入口启动脚本
- `setsid + nohup` 后台运行
- 固定日志目录和 PID 文件
- `--strictPort` 防止端口漂移
- 启动后做健康检查，失败直接退出

## 脚本

- 启动：`scripts/lan/start.sh`
- 状态：`scripts/lan/status.sh`
- 停止：`scripts/lan/stop.sh`

运行目录约定：

- PID：`.runtime/lan/pids/`
- 日志：`.runtime/lan/logs/`

## 启动

在仓库根目录执行：

```bash
scripts/lan/start.sh
```

默认端口：

- backend: `127.0.0.1:18001`
- frontend: `0.0.0.0:15173`

可用环境变量覆盖：

```bash
LEON_BACKEND_PORT=8001 LEON_FRONTEND_PORT=5173 scripts/lan/start.sh
```

## 访问方式

启动成功后脚本会打印：

- `frontend_local_url`
- `frontend_lan_url`

你在 Mac mini 上用 `frontend_lan_url` 打开即可。

## 例行检查

```bash
scripts/lan/status.sh
curl -fsS http://127.0.0.1:18001/openapi.json >/dev/null
curl -fsS http://127.0.0.1:15173/resources >/dev/null
```

## 停止

```bash
scripts/lan/stop.sh
```

## 失败排查

- 看后端错误日志：`.runtime/lan/logs/backend.err.log`
- 看前端错误日志：`.runtime/lan/logs/frontend.err.log`
- 若端口冲突，先执行 `scripts/lan/stop.sh`，再重启
