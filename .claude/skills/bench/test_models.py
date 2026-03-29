#!/usr/bin/env python3
"""
Test model performance: TTFB and token generation speed.
"""

import asyncio
import sys
import time

import aiohttp

# Get parameters from command line
if len(sys.argv) < 3:
    print("Error: API_KEY and BASE_URL are required")
    print("Usage: python test_models.py <API_KEY> <BASE_URL>")
    print("Example: python test_models.py sk-xxx https://api.example.com/v1")
    sys.exit(1)

API_KEY = sys.argv[1]
BASE_URL = sys.argv[2]

TEST_PROMPT = "请写一篇300字的短文，主题是春天的早晨。"


async def fetch_models(session):
    """Fetch available models from /models endpoint."""
    try:
        async with session.get(f"{BASE_URL}/models", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                models = [m["id"] for m in data.get("data", [])]
                return models
            else:
                print(f"Warning: Failed to fetch models (HTTP {resp.status}), using defaults")
                return None
    except Exception as e:
        print(f"Warning: Failed to fetch models ({e}), using defaults")
        return None


# Default models if /models endpoint fails
DEFAULT_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "gpt-5.2-2025-12-11",
    "gpt-5.1-2025-11-13",
    "qwen3-max-2026-01-23",
    "glm-4.7",
    "kimi-k2.5",
]


async def test_model_streaming(session, model):
    """Test a model with streaming to measure TTFB and token speed."""
    start_time = time.time()
    first_token_time = None
    tokens_received = 0
    content_length = 0

    try:
        async with session.post(
            f"{BASE_URL}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "stream": True,
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                try:
                    text = await resp.text()
                    return {"model": model, "status": "✗", "error": text[:50]}
                except Exception:
                    return {"model": model, "status": "✗", "error": f"HTTP {resp.status}"}

            try:
                async for line in resp.content:
                    # Check TTFB timeout (10s)
                    if first_token_time is None and (time.time() - start_time) > 10:
                        return {"model": model, "status": "✗", "error": "TTFB timeout (>10s)"}

                    # Check total timeout (30s)
                    if (time.time() - start_time) > 30:
                        return {"model": model, "status": "✗", "error": "Total timeout (>30s)"}

                    if not line:
                        continue

                    line = line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        import json

                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")

                        if content:
                            if first_token_time is None:
                                first_token_time = time.time()
                            tokens_received += 1
                            content_length += len(content)

                    except json.JSONDecodeError:
                        continue
                    except Exception:
                        continue

            except Exception as e:
                if tokens_received > 0:
                    # Partial success
                    total_time = time.time() - start_time
                    ttfb = first_token_time - start_time if first_token_time else None
                    generation_time = total_time - ttfb if ttfb else total_time
                    tokens_per_sec = tokens_received / generation_time if generation_time > 0 else 0

                    return {
                        "model": model,
                        "status": "⚠",
                        "ttfb": ttfb,
                        "total_time": total_time,
                        "tokens": tokens_received,
                        "chars": content_length,
                        "tokens_per_sec": tokens_per_sec,
                        "error": f"Partial: {str(e)[:30]}",
                    }
                else:
                    return {"model": model, "status": "✗", "error": str(e)[:50]}

        total_time = time.time() - start_time
        ttfb = first_token_time - start_time if first_token_time else None

        if ttfb is None:
            return {"model": model, "status": "✗", "error": "No tokens received"}

        generation_time = total_time - ttfb
        tokens_per_sec = tokens_received / generation_time if generation_time > 0 else 0

        return {
            "model": model,
            "status": "✓",
            "ttfb": ttfb,
            "total_time": total_time,
            "tokens": tokens_received,
            "chars": content_length,
            "tokens_per_sec": tokens_per_sec,
        }

    except TimeoutError:
        return {"model": model, "status": "✗", "error": "Timeout (>30s)"}
    except Exception as e:
        return {"model": model, "status": "✗", "error": str(e)[:50]}


async def main():
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession(headers=headers) as session:
        # Fetch available models
        print("Fetching available models...")
        all_models = await fetch_models(session)

        if all_models:
            # Filter for latest mainstream text models only
            test_models = []

            # Claude: 4.6, 4.5, 4-5 (排除 3.x)
            claude_models = [
                m
                for m in all_models
                if "claude" in m.lower()
                and any(v in m for v in ["4.6", "4.5", "4-6", "4-5"])
                and not any(skip in m.lower() for skip in ["embed", "vision", "3."])
            ]
            test_models.extend(claude_models)

            # GPT: 5.x (排除 4.x, o1, o3)
            gpt_models = [
                m
                for m in all_models
                if "gpt" in m.lower()
                and ("5." in m or "gpt-5" in m.lower())
                and not any(skip in m.lower() for skip in ["embed", "audio", "realtime", "vision", "4.", "4o", "4.1"])
            ]
            test_models.extend(gpt_models)

            # Gemini: 3.x (排除 2.x)
            gemini_models = [
                m
                for m in all_models
                if "gemini" in m.lower()
                and ("3" in m or "gemini-3" in m.lower())
                and not any(skip in m.lower() for skip in ["embed", "vision", "lite", "image", "2."])
            ]
            test_models.extend(gemini_models)

            # Qwen: 3.x (排除 2.x)
            qwen_models = [
                m
                for m in all_models
                if "qwen" in m.lower()
                and ("qwen3" in m.lower() or "qwen-3" in m.lower())
                and not any(skip in m.lower() for skip in ["embed", "vl", "vision", "coder", "math", "2."])
            ]
            test_models.extend(qwen_models)

            # GLM: 4.7+ (排除 4.6 及以下)
            glm_models = [
                m
                for m in all_models
                if "glm" in m.lower()
                and ("4.7" in m or "glm-4.7" in m.lower())
                and not any(skip in m.lower() for skip in ["embed", "vision", "4.6", "4.5"])
            ]
            test_models.extend(glm_models)

            # Kimi: k2.5+ (排除 k2 及以下)
            kimi_models = [
                m
                for m in all_models
                if "kimi" in m.lower()
                and ("k2.5" in m.lower() or "k3" in m.lower())
                and not any(skip in m.lower() for skip in ["embed", "vision"])
            ]
            test_models.extend(kimi_models)

            # 排除 DeepSeek (按要求不测)

            # 去重
            test_models = list(dict.fromkeys(test_models))

            if not test_models:
                print("No suitable latest models found, using defaults")
                test_models = DEFAULT_MODELS
        else:
            test_models = DEFAULT_MODELS

        print(f"Testing {len(test_models)} models with streaming...")
        print(f"Task: {TEST_PROMPT}\n")

        tasks = [test_model_streaming(session, model) for model in test_models]
        results = await asyncio.gather(*tasks)

    # Separate successful and failed results
    successful = [r for r in results if r["status"] in ["✓", "⚠"]]
    failed = [r for r in results if r["status"] == "✗"]

    # Sort by TTFB first, then by token speed
    successful.sort(key=lambda x: (x.get("ttfb", 999), -x.get("tokens_per_sec", 0)))

    print("=" * 90)
    print(f"{'Model':<40} {'TTFB':<12} {'Tok/s':<12} {'Status'}")
    print("=" * 90)

    for r in successful:
        print(f"{r['model']:<40} {r['ttfb']:.2f}s       {r['tokens_per_sec']:>6.1f}       {r['status']}")

    for r in failed:
        print(f"{r['model']:<40} {'--':<12} {'--':<12} ✗ {r.get('error', '')[:20]}")

    # Summary
    if successful:
        fastest_ttfb = min(successful, key=lambda x: x["ttfb"])
        fastest_tokens = max(successful, key=lambda x: x["tokens_per_sec"])

        print("=" * 90)
        print(f"🏆 最快首次响应: {fastest_ttfb['model']} ({fastest_ttfb['ttfb']:.2f}s)")
        print(f"⚡ 最快吐字速度: {fastest_tokens['model']} ({fastest_tokens['tokens_per_sec']:.1f} tok/s)")
        print(f"✓ {len(successful)}/{len(results)} 模型可用")


if __name__ == "__main__":
    asyncio.run(main())
