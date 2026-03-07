# Leon 调试经验

## 问题：Agent 卡死，前端无响应

**症状**：
- 用户发送消息后，前端一直等待，没有任何响应
- 后端日志显示 `openai.APIConnectionError: Connection error.`
- 前端没有显示错误信息

**调试步骤**：

1. **检查最新 thread**：
   ```bash
   sqlite3 ~/.leon/leon.db "SELECT DISTINCT thread_id FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 5"
   ```

2. **查看 thread 消息历史**：
   ```bash
   curl -s http://127.0.0.1:8001/api/threads/<thread_id> | python3 -m json.tool
   ```
   - 如果最后一条是 HumanMessage，说明 Agent 没有回复

3. **检查后端日志**：
   ```bash
   tail -100 /tmp/leon-backend.log | grep -E "error|Error|Exception"
   ```
   - 找到 `APIConnectionError` 或其他异常

4. **验证 API 可达性**：
   ```bash
   curl -s http://<api_endpoint>/v1/models
   ```

**根本原因**：

在 `services/web/main.py` 的 `event_stream()` 函数中：
- Agent stream 的异常发生在 `await task` (line 1270)
- 只捕获了 `StopAsyncIteration`，其他异常（如 `APIConnectionError`）会传播出去
- 虽然外层有 `except Exception` (line 1444)，但异常发生在 while 循环内部
- **问题**：异常导致 generator 直接停止，没有 yield error 事件给前端

**解决方案**：

在 while 循环中添加异常捕获：

```python
# services/web/main.py:1267-1282
while True:
    try:
        chunk = await task
        task = asyncio.create_task(stream_gen.__anext__())
        app.state.thread_tasks[thread_id] = task
    except StopAsyncIteration:
        break
    except Exception as stream_error:  # ← 新增
        import traceback
        traceback.print_exc()
        yield {"event": "error", "data": json.dumps({"error": str(stream_error)}, ensure_ascii=False)}
        break
```

**效果**：
- ✅ API 连接错误会被捕获并发送 `error` 事件给前端
- ✅ 前端显示错误信息，用户知道发生了什么
- ✅ 不会出现"卡死"的假象

**关键教训**：
- 异步 generator 的异常处理需要在 `await` 点捕获
- 不能依赖外层的 `except Exception`，因为 generator 会在异常时直接停止
- 前端必须能看到后端的错误信息，否则用户无法判断问题

## Token 监控调试方法

### 调试思路

当 token 数据异常（不同模型差异大、数值为 0、与 Langfuse 不一致）时：

1. **写一次性诊断脚本**，直接 `astream` 发一条消息，dump 原始 `usage_metadata` 和 `response_metadata`
2. **对比多个 provider**，确认差异来自 API 还是 Leon 的处理逻辑
3. **用 Langfuse 交叉验证**，对比 Leon monitor 和 Langfuse GENERATION 观测的 token 数

### Token 数据链路

```
LLM API response
  → LangChain adapter (ChatAnthropic/ChatOpenAI)
  → AIMessage.usage_metadata     ← TokenMonitor + ContextMonitor 读取
  → AIMessage.response_metadata  ← TokenMonitor 回退路径
  → Langfuse GENERATION span     ← 独立记录（通过 LangfuseHandler callback）
```

关键检查点：
- `usage_metadata` 是否存在（代理/兼容层可能丢失）
- `input_tokens` 是否 > 0（streaming 模式需要 `stream_usage=True`）
- `input_token_details` 中的 cache 字段（仅 Anthropic 有）

### 诊断脚本模板

```python
"""一次性脚本，用完即删。核心：dump AIMessage 的原始 usage 数据"""
import asyncio, json, uuid
from agent import LeonAgent

async def main(model: str | None = None):
    agent = LeonAgent(model_name=model)
    thread_id = f"debug-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    async for chunk in agent.agent.astream(
        {"messages": [{"role": "user", "content": "Hello"}]},
        config=config, stream_mode="updates",
    ):
        for key, val in chunk.items():
            if isinstance(val, dict) and "messages" in val:
                for msg in val["messages"]:
                    usage = getattr(msg, "usage_metadata", None)
                    resp = getattr(msg, "response_metadata", None)
                    print(f"[{key}] usage_metadata: {dict(usage) if usage else None}")
                    if resp:
                        print(f"  response_metadata: {
                            {k: v for k, v in resp.items() if 'usage' in k.lower() or 'token' in k.lower()}
                        }")

    if hasattr(agent, "runtime"):
        print(json.dumps(agent.runtime.get_status_dict(), indent=2))
    agent.close()

if __name__ == "__main__":
    import sys
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
```

### Langfuse 查询

```bash
# 查最近 trace
uv run python examples/langfuse_query.py traces 5

# 查某个 thread 的完整 session（含每次 LLM 调用的 token 明细）
uv run python examples/langfuse_query.py session <thread_id>
```

Langfuse 中只有 `GENERATION` 类型的 observation 有 token 数据，`TOOL` 类型没有。

### 已知的 provider 差异（非 bug）

| 项目 | Anthropic | OpenAI |
|------|-----------|--------|
| `input_tokens` 含义 | 总量（含 cache_read + cache_write） | 总量（含 cached_tokens） |
| cache 字段 | `cache_read` / `cache_creation` in `input_token_details` | `cache_read` in `input_token_details` |
| reasoning 字段 | 无 | `reasoning` in `output_token_details`（o1/o3） |
| 同内容 token 数 | 较高（~2.3x） | 较低（基准） |
| streaming usage | 需要 `usage_patches.py` 修复 `message_start` | 需要 `stream_usage=True` |

同一条 "Hello" 消息（含 system prompt + tool definitions），Anthropic ~5700 tokens，OpenAI ~2500 tokens。差异来自 tokenizer 和 tool schema 格式，不是 bug。
