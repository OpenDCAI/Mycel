[🇬🇧 English](../en/cli.md) | 🇨🇳 中文

# CLI / TUI 参考

Mycel 包含终端界面，用于快速交互、脚本化操作和沙箱管理。项目的主界面是 [Web UI](../../README.zh.md#快速开始)——CLI 是面向开发者和高级用户的补充工具。

## 安装

```bash
pip install leonai
# 或
uv tool install leonai
```

## 首次运行

```bash
leonai
```

如果未检测到 API 密钥，交互式配置向导会自动启动：

1. **API_KEY**（必填）— OpenAI 兼容的 API 密钥
2. **BASE_URL**（可选）— API 端点，默认 `https://api.openai.com/v1`
3. **MODEL_NAME**（可选）— 使用的模型，默认 `claude-sonnet-4-5-20250929`

配置保存到 `~/.leon/config.env`。

```bash
leonai config          # 重新运行向导
leonai config show     # 查看当前设置
```

## 使用

```bash
leonai                          # 开始新对话
leonai -c                       # 继续上次对话
leonai --thread <thread-id>     # 恢复指定对话
leonai --model gpt-4o           # 使用指定模型
leonai --workspace /path/to/dir # 设置工作目录
```

## 对话管理

```bash
leonai thread ls                          # 列出所有对话
leonai thread history <thread-id>         # 查看对话历史
leonai thread rewind <thread-id> <cp-id>  # 回退到检查点
leonai thread rm <thread-id>              # 删除对话
```

## 非交互模式

```bash
leonai run "解释这个代码库"                  # 单条消息
echo "总结一下" | leonai run --stdin        # 从 stdin 读取
leonai run -i                               # 无 TUI 交互模式
```

## 沙箱管理

```bash
leonai sandbox              # 打开沙箱管理 TUI
leonai sandbox ls           # 列出活跃会话
leonai sandbox new docker   # 创建新 Docker 会话
leonai sandbox metrics <id> # 查看资源使用
```

## LLM 提供商示例

Mycel 使用 OpenAI 兼容 API 格式，支持任何兼容的提供商。

| 提供商 | BASE_URL | MODEL_NAME |
|--------|----------|------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4-5-20250929` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |

环境变量优先于 `~/.leon/config.env`：

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4o"
```
