# 开发规范

## 本地测试

修改代码后本地测试：

```bash
uv cache clean leonai --force && uv tool install . --force
```

- `--force` 必须加，否则缓存/进程占用会导致安装旧版本

## 发版

- push tag → GitHub Actions 自动发布到 PyPI
- ❌ 不要用 `uv publish`
