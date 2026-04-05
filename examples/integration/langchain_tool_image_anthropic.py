import base64
import os
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model


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


def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Missing required env var: {key}")
    return value


def _repo_image_png_base64() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    image_path = repo_root / "image.png"
    if not image_path.exists():
        raise FileNotFoundError(str(image_path))
    raw = image_path.read_bytes()
    return base64.b64encode(raw).decode("ascii")


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

    env_model_name = os.environ.get("MODEL_NAME")
    model_name = env_model_name or "claude-sonnet-4-5-20250929"
    if not model_name.lower().startswith("claude-"):
        model_name = "claude-sonnet-4-5-20250929"

    base_url = os.environ.get("OPENAI_BASE_URL")

    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_core.tools import tool

    @tool(description="Return repo image.png as an Anthropic-compatible image content block.")
    def make_test_image() -> list[dict[str, str]]:
        return [
            {
                "type": "image",
                "mime_type": "image/png",
                "base64": _repo_image_png_base64(),
            }
        ]

    model_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        model_kwargs["base_url"] = base_url

    llm = init_chat_model(model_name, **model_kwargs)
    llm_with_tools = llm.bind_tools([make_test_image])

    messages: list[Any] = [
        HumanMessage(
            content=(
                "请调用工具 make_test_image。"
                "工具会返回一张图片作为 content blocks（不是文本/URL）。"
                "收到工具结果后，请描述图片内容。"
            )
        )
    ]

    first = llm_with_tools.invoke(messages)
    tool_calls = getattr(first, "tool_calls", None) or []
    if not tool_calls:
        raise RuntimeError("Model did not produce tool_calls")

    call0 = tool_calls[0]
    tool_call_id = call0.get("id") or call0.get("tool_call_id")
    if call0.get("name") != "make_test_image":
        raise RuntimeError(f"Unexpected tool name: {call0.get('name')}")

    tool_result = make_test_image.invoke(call0.get("args") or {})
    tool_message = ToolMessage(content_blocks=tool_result, tool_call_id=tool_call_id)

    messages.append(first)
    messages.append(tool_message)

    final = llm.invoke(messages)

    model_used = getattr(final, "response_metadata", {}).get("model") or model_name
    message_id = getattr(final, "id", None)
    print(f"provider=anthropic model={model_used} message_id={message_id}")
    print(_extract_text_content(getattr(final, "content", "")))


if __name__ == "__main__":
    main()
