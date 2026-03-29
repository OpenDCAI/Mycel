#!/usr/bin/env python3
"""
Test Anthropic native API (/v1/messages) performance: TTFB and token speed.
"""

import asyncio
import json
import sys
import time

import aiohttp

if len(sys.argv) < 3:
    print("Usage: python test_anthropic.py <API_KEY> <BASE_URL>")
    print("Example: python test_anthropic.py sk-ant-xxx https://api.example.com/claude/droid")
    sys.exit(1)

API_KEY = sys.argv[1]
BASE_URL = sys.argv[2].rstrip("/")

# Strip /v1 suffix if present — we'll add it ourselves
if BASE_URL.endswith("/v1"):
    BASE_URL = BASE_URL[:-3]

TEST_PROMPT = "请写一篇300字的短文，主题是春天的早晨。"

DEFAULT_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]


async def test_model(session, model):
    """Test a single model with Anthropic streaming."""
    start_time = time.time()
    first_token_time = None
    chunks_received = 0
    content_length = 0
    output_tokens = 0

    try:
        async with session.post(
            f"{BASE_URL}/v1/messages",
            json={
                "model": model,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "max_tokens": 4096,
                "stream": True,
            },
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            if resp.status != 200:
                try:
                    text = await resp.text()
                    # Try to parse error JSON
                    err = json.loads(text).get("error", {}).get("message", text[:60])
                except Exception:
                    err = text[:60]
                return {"model": model, "status": "✗", "error": err[:60]}

            async for raw_line in resp.content:
                if first_token_time is None and (time.time() - start_time) > 10:
                    return {"model": model, "status": "✗", "error": "TTFB timeout (>10s)"}
                if (time.time() - start_time) > 90:
                    return {"model": model, "status": "✗", "error": "Total timeout (>30s)"}

                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type", "")

                if event_type == "content_block_delta":
                    text = data.get("delta", {}).get("text", "")
                    if text:
                        if first_token_time is None:
                            first_token_time = time.time()
                        chunks_received += 1
                        content_length += len(text)

                elif event_type == "message_delta":
                    usage = data.get("usage", {})
                    output_tokens = usage.get("output_tokens", 0)

                elif event_type == "message_stop":
                    break

        total_time = time.time() - start_time
        ttfb = first_token_time - start_time if first_token_time else None

        if ttfb is None:
            return {"model": model, "status": "✗", "error": "No tokens received"}

        gen_time = total_time - ttfb
        tok_s = output_tokens / gen_time if gen_time > 0 else 0

        return {
            "model": model, "status": "✓",
            "ttfb": ttfb, "total_time": total_time,
            "tokens": output_tokens, "chars": content_length,
            "tokens_per_sec": tok_s,
        }

    except TimeoutError:
        return {"model": model, "status": "✗", "error": "Timeout (>30s)"}
    except Exception as e:
        return {"model": model, "status": "✗", "error": str(e)[:60]}


async def main():
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    print(f"Endpoint: {BASE_URL}/v1/messages")
    print(f"Testing {len(DEFAULT_MODELS)} models with streaming...")
    print(f"Task: {TEST_PROMPT}\n")

    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [test_model(session, m) for m in DEFAULT_MODELS]
        results = await asyncio.gather(*tasks)

    ok = [r for r in results if r["status"] in ("✓", "⚠")]
    fail = [r for r in results if r["status"] == "✗"]
    ok.sort(key=lambda x: (x.get("ttfb", 999), -x.get("tokens_per_sec", 0)))

    print("=" * 90)
    print(f"{'Model':<40} {'TTFB':<12} {'Tok/s':<12} {'Status'}")
    print("=" * 90)

    for r in ok:
        print(f"{r['model']:<40} {r['ttfb']:.2f}s       {r['tokens_per_sec']:>6.1f}       {r['status']}")
    for r in fail:
        print(f"{r['model']:<40} {'--':<12} {'--':<12} ✗ {r.get('error', '')[:40]}")

    if ok:
        best_ttfb = min(ok, key=lambda x: x["ttfb"])
        best_tok = max(ok, key=lambda x: x["tokens_per_sec"])
        print("=" * 90)
        print(f"🏆 最快首次响应: {best_ttfb['model']} ({best_ttfb['ttfb']:.2f}s)")
        print(f"⚡ 最快吐字速度: {best_tok['model']} ({best_tok['tokens_per_sec']:.1f} tok/s)")
        print(f"✓ {len(ok)}/{len(results)} 模型可用")


if __name__ == "__main__":
    asyncio.run(main())
