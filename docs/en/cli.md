🇬🇧 English | [🇨🇳 中文](../zh/cli.md)

# CLI / TUI Reference

Mycel includes a terminal interface for quick interactions, scripting, and sandbox management. The primary interface is the [Web UI](../../README.md#quick-start) — the CLI is a complementary tool for power users and development.

## Installation

```bash
pip install leonai
# or
uv tool install leonai
```

## First Run

```bash
leonai
```

If no API key is detected, the interactive config wizard starts automatically:

1. **API_KEY** (required) — Your OpenAI-compatible API key
2. **BASE_URL** (optional) — API endpoint, defaults to `https://api.openai.com/v1`
3. **MODEL_NAME** (optional) — Model to use, defaults to `claude-sonnet-4-5-20250929`

Configuration is saved to `~/.leon/config.env`.

```bash
leonai config          # Re-run wizard
leonai config show     # View current settings
```

## Usage

```bash
leonai                          # Start a new conversation
leonai -c                       # Continue last conversation
leonai --thread <thread-id>     # Resume a specific thread
leonai --model gpt-4o           # Use a specific model
leonai --workspace /path/to/dir # Set working directory
```

## Thread Management

```bash
leonai thread ls                          # List all conversations
leonai thread history <thread-id>         # View conversation history
leonai thread rewind <thread-id> <cp-id>  # Rewind to checkpoint
leonai thread rm <thread-id>              # Delete a thread
```

## Non-interactive Mode

```bash
leonai run "Explain this codebase"            # Single message
echo "Summarize this" | leonai run --stdin    # Read from stdin
leonai run -i                                  # Interactive without TUI
```

## Sandbox Management

```bash
leonai sandbox              # Open sandbox manager TUI
leonai sandbox ls           # List active sessions
leonai sandbox new docker   # Create a new Docker session
leonai sandbox metrics <id> # View resource usage
```

## LLM Provider Examples

Mycel uses the OpenAI-compatible API format. Any provider that speaks this protocol works.

| Provider | BASE_URL | MODEL_NAME |
|----------|----------|------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4-5-20250929` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |

Environment variables override `~/.leon/config.env`:

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4o"
```
