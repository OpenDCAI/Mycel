"""Test read_file image support with Claude model."""

import os
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, ToolMessage

from core.tools.filesystem.read import read_file


def _load_dotenv_if_present() -> None:
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts).strip()
    return str(content)


def main() -> None:
    _load_dotenv_if_present()

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required env var: OPENAI_API_KEY (or ANTHROPIC_API_KEY)")

    model_name = os.environ.get("MODEL_NAME") or "claude-sonnet-4-5-20250929"
    base_url = os.environ.get("OPENAI_BASE_URL")

    model_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        model_kwargs["base_url"] = base_url

    llm = init_chat_model(model_name, **model_kwargs)

    image_path = Path(__file__).resolve().parents[1] / "image.png"
    result = read_file(image_path)

    print("# read_file result")
    print(f"file_path: {result.file_path}")
    print(f"content_blocks: {bool(result.content_blocks)}")
    if result.content_blocks:
        print(f"  block type: {result.content_blocks[0].get('type')}")
        print(f"  mime_type: {result.content_blocks[0].get('mime_type')}")

    if not result.content_blocks:
        raise RuntimeError("read_file did not return content_blocks for image")

    tool_call_id = "test_read_file_001"
    tool_message = ToolMessage(content_blocks=result.content_blocks, tool_call_id=tool_call_id)

    messages: list[Any] = [
        HumanMessage(content="我会给你一张图片，请描述图片内容。"),
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        tool_message,
    ]

    print("\n# Invoking model...")
    final = llm.invoke(messages)

    model_used = getattr(final, "response_metadata", {}).get("model") or model_name
    print(f"\n# Model response (model={model_used})")
    print(_extract_text_content(getattr(final, "content", "")))


if __name__ == "__main__":
    main()
