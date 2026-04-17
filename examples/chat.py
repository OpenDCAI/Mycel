#!/usr/bin/env python3
"""
Leon Agent 交互式聊天 - 流式输出 + 工具调用展示

特点：
- 流式输出 agent 响应
- 实时展示工具调用过程
- 彩色输出，清晰展示不同阶段
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env
env_file = project_root / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value

from core.runtime.agent import create_leon_agent


class Colors:
    """终端颜色"""

    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_banner():
    """打印欢迎横幅"""
    print(f"\n{Colors.CYAN}{'=' * 70}")
    print(f"{Colors.BOLD}  Leon Agent - 交互式聊天{Colors.RESET}")
    print(f"{Colors.CYAN}  流式输出 + 工具调用展示")
    print(f"{'=' * 70}{Colors.RESET}\n")


def print_tool_call(tool_name: str, tool_input: dict):
    """打印工具调用信息"""
    print(f"\n{Colors.YELLOW}🔧 调用工具: {Colors.BOLD}{tool_name}{Colors.RESET}")

    # 格式化输入参数
    if tool_input:
        print(f"{Colors.YELLOW}   参数:{Colors.RESET}")
        for key, value in tool_input.items():
            # 截断长值
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:100] + "..."
            print(f"{Colors.YELLOW}     {key}: {Colors.RESET}{value_str}")
    print()


def print_tool_result(tool_name: str, result: str):
    """打印工具返回值"""
    print(f"{Colors.CYAN}📤 工具返回:{Colors.RESET}")

    # 截断长返回值
    result_str = str(result)
    if len(result_str) > 500:
        result_str = result_str[:500] + f"... (共 {len(result_str)} 字符)"

    # 多行结果缩进显示
    for line in result_str.splitlines():
        print(f"{Colors.CYAN}   {Colors.RESET}{line}")
    print()


def stream_response(agent, message: str, thread_id: str = "chat"):
    """流式处理 agent 响应并展示工具调用"""
    print(f"{Colors.GREEN}🤖 Leon:{Colors.RESET} ", end="", flush=True)

    try:
        config = {"configurable": {"thread_id": thread_id}}

        # 跟踪已显示的内容
        last_ai_content = None
        shown_tool_calls = set()
        shown_tool_results = set()

        # LangChain 的 stream 方法
        for chunk in agent.agent.stream({"messages": [{"role": "user", "content": message}]}, config=config, stream_mode="values"):
            # 获取最新的消息
            if "messages" in chunk and chunk["messages"]:
                last_msg = chunk["messages"][-1]

                # 检查是否是 AI 消息且有新内容
                if hasattr(last_msg, "content") and last_msg.content:
                    if last_msg.content != last_ai_content:
                        # 只显示 AI 消息（不是用户消息）
                        if last_msg.__class__.__name__ == "AIMessage":
                            print(last_msg.content, end="", flush=True)
                            last_ai_content = last_msg.content

                # 检查工具调用
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    for tool_call in last_msg.tool_calls:
                        tool_id = tool_call.get("id", "")
                        if tool_id and tool_id not in shown_tool_calls:
                            print()  # 换行
                            print_tool_call(tool_call.get("name", "unknown"), tool_call.get("args", {}))
                            shown_tool_calls.add(tool_id)

                # 检查工具返回值
                if last_msg.__class__.__name__ == "ToolMessage":
                    tool_call_id = getattr(last_msg, "tool_call_id", None)
                    if tool_call_id and tool_call_id not in shown_tool_results:
                        tool_name = getattr(last_msg, "name", "unknown")
                        print_tool_result(tool_name, last_msg.content)
                        shown_tool_results.add(tool_call_id)

        print()  # 换行

    except Exception as e:
        print(f"\n{Colors.RED}❌ 错误: {e}{Colors.RESET}")
        import traceback

        traceback.print_exc()


def main():
    """主函数"""
    print_banner()

    # 检查 API key
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print(f"{Colors.RED}❌ 错误: 未设置 API key{Colors.RESET}")
        print("\n请设置环境变量：")
        print("  export ANTHROPIC_API_KEY='your-key'")
        print("  或")
        print("  export OPENAI_API_KEY='your-key'  # 如果使用代理")
        return

    # 创建 agent
    print(f"{Colors.BLUE}🚀 初始化 Leon Agent...{Colors.RESET}")
    agent = create_leon_agent()
    print(f"{Colors.GREEN}✅ Agent 已就绪{Colors.RESET}")
    print(f"{Colors.BLUE}📁 工作目录: {agent.workspace_root}{Colors.RESET}\n")

    print(f"{Colors.CYAN}提示:{Colors.RESET}")
    print("  - 输入 'exit' 或 'quit' 退出")
    print("  - 输入 'clear' 清空对话历史")
    print("  - 所有文件操作都在工作目录内进行\n")

    thread_id = "interactive-chat"

    try:
        while True:
            # 获取用户输入
            try:
                user_input = input(f"{Colors.MAGENTA}👤 你:{Colors.RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n\n{Colors.YELLOW}👋 再见！{Colors.RESET}")
                break

            if not user_input:
                continue

            # 处理特殊命令
            if user_input.lower() in ["exit", "quit", "q"]:
                print(f"\n{Colors.YELLOW}👋 再见！{Colors.RESET}")
                break

            if user_input.lower() == "clear":
                thread_id = f"interactive-chat-{os.urandom(4).hex()}"
                print(f"{Colors.GREEN}✓ 对话历史已清空{Colors.RESET}\n")
                continue

            # 流式处理响应
            stream_response(agent, user_input, thread_id)
            print()  # 空行分隔

    finally:
        # 清理
        agent.cleanup()
        print(f"\n{Colors.BLUE}🧹 工作目录已清理{Colors.RESET}")


if __name__ == "__main__":
    main()
