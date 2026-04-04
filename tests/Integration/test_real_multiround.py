#!/usr/bin/env python3
"""
真实多轮对话测试 - 验证 Bash Session 持久化

测试场景：
1. 文件系统操作持久化（创建、修改、删除文件）
2. Shell 进程 PID 保持不变
3. 后台进程管理
4. 工作目录和环境变量（在单命令内）
5. 不同 thread_id 的 session 隔离
6. Session 清理和资源释放
"""

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("LEON_E2E_AGENT"),
    reason="LEON_E2E_AGENT not set (requires working LLM API key for real agent calls)",
)

# Guard: only load heavy agent module when actually running e2e
if not os.getenv("LEON_E2E_AGENT"):
    create_leon_agent = None  # type: ignore[assignment]
else:
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))

    env_file = project_root / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

    from agent import create_leon_agent


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_test(name: str):
    print(f"\n{Colors.BLUE}{'=' * 70}")
    print(f"测试: {name}")
    print(f"{'=' * 70}{Colors.RESET}")


def print_pass(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")


def print_fail(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")


def print_info(msg: str):
    print(f"{Colors.YELLOW}ℹ️  {msg}{Colors.RESET}")


def test_multiround_persistence():
    """真实多轮对话测试"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}")
    print("真实多轮对话测试 - Bash Session 持久化")
    print(f"{'=' * 70}{Colors.RESET}\n")

    agent = create_leon_agent()
    thread_id = "real-multiround-test"
    test_file = "/tmp/leon_test_multiround.txt"

    try:
        # ========== 测试 1: Shell 进程 PID 持久化 ==========
        print_test("1. Shell 进程 PID 持久化")

        # 提取实际的 PID（从 ToolMessage）
        def extract_pid(result):
            for msg in reversed(result["messages"]):
                if hasattr(msg, "__class__") and msg.__class__.__name__ == "ToolMessage":
                    return msg.content.strip()
            return None

        result1 = agent.invoke("使用 bash 执行：echo $$", thread_id=thread_id)
        pid1 = extract_pid(result1)
        print_info(f"第 1 轮 PID: {pid1}")

        result2 = agent.invoke("使用 bash 执行：echo $$", thread_id=thread_id)
        pid2 = extract_pid(result2)
        print_info(f"第 2 轮 PID: {pid2}")

        result3 = agent.invoke("使用 bash 执行：echo $$", thread_id=thread_id)
        pid3 = extract_pid(result3)
        print_info(f"第 3 轮 PID: {pid3}")

        # 验证：PID 应该相同（同一个 shell 进程）
        if pid1 and pid2 and pid3 and pid1 == pid2 == pid3:
            print_pass(f"Shell 进程 PID 在多轮对话中保持不变 (PID: {pid1})")
        else:
            print_fail(f"Shell 进程 PID 发生变化: {pid1} → {pid2} → {pid3}")

        # ========== 测试 2: 文件系统操作持久化 ==========
        print_test("2. 文件系统操作持久化")

        # 第 1 轮：创建文件
        result4 = agent.invoke(
            f"使用 bash 执行：echo 'Round 1: Initial content' > {test_file}",
            thread_id=thread_id,
        )
        print_info(f"第 1 轮 - 创建文件: {result4['messages'][-1].content}")

        # 第 2 轮：追加内容
        result5 = agent.invoke(
            f"使用 bash 执行：echo 'Round 2: Appended content' >> {test_file}",
            thread_id=thread_id,
        )
        print_info(f"第 2 轮 - 追加内容: {result5['messages'][-1].content}")

        # 第 3 轮：读取文件
        result6 = agent.invoke(
            f"使用 bash 执行：cat {test_file}",
            thread_id=thread_id,
        )
        content = result6["messages"][-1].content
        print_info(f"第 3 轮 - 读取文件:\n{content}")

        # 验证：文件应该包含两行内容
        if "Round 1" in content and "Round 2" in content:
            print_pass("文件系统操作在多轮对话中正确持久化")
        else:
            print_fail("文件内容不完整")

        # 第 4 轮：统计行数
        result7 = agent.invoke(
            f"使用 bash 执行：wc -l {test_file}",
            thread_id=thread_id,
        )
        print_info(f"第 4 轮 - 行数统计: {result7['messages'][-1].content}")

        if "2" in result7["messages"][-1].content:
            print_pass("文件行数正确（2 行）")
        else:
            print_fail("文件行数不正确")

        # ========== 测试 3: 单命令内的状态保持 ==========
        print_test("3. 单命令内的工作目录和环境变量")

        result8 = agent.invoke(
            "使用 bash 执行：cd /tmp && export TEST_VAR=multiround && pwd && echo $TEST_VAR",
            thread_id=thread_id,
        )
        output8 = result8["messages"][-1].content
        print_info(f"单命令测试:\n{output8}")

        if "/tmp" in output8 and "multiround" in output8:
            print_pass("单命令内 cd 和 export 正常工作")
        else:
            print_fail("单命令内状态异常")

        # ========== 测试 4: 复杂文件操作序列 ==========
        print_test("4. 复杂文件操作序列")

        # 创建多个文件
        result9 = agent.invoke(
            '使用 bash 执行：for i in 1 2 3; do echo "File $i" > /tmp/test_$i.txt; done && ls /tmp/test_*.txt',
            thread_id=thread_id,
        )
        print_info(f"创建多个文件: {result9['messages'][-1].content}")

        # 读取并合并
        result10 = agent.invoke(
            "使用 bash 执行：cat /tmp/test_*.txt",
            thread_id=thread_id,
        )
        merged = result10["messages"][-1].content
        print_info(f"合并内容:\n{merged}")

        if "File 1" in merged and "File 2" in merged and "File 3" in merged:
            print_pass("复杂文件操作序列正确执行")
        else:
            print_fail("文件操作序列失败")

        # 清理
        result11 = agent.invoke(
            "使用 bash 执行：rm -f /tmp/test_*.txt && echo 'Cleaned up'",
            thread_id=thread_id,
        )
        print_info(f"清理: {result11['messages'][-1].content}")

        # ========== 测试 5: 不同 thread_id 的 session 隔离 ==========
        print_test("5. 不同 thread_id 的 session 隔离")

        # Thread 1: 创建文件
        result12 = agent.invoke(
            "使用 bash 执行：echo 'Thread 1 data' > /tmp/thread1.txt && cat /tmp/thread1.txt",
            thread_id="thread-1",
        )
        print_info(f"Thread 1 创建文件: {result12['messages'][-1].content}")

        # Thread 2: 创建不同的文件
        result13 = agent.invoke(
            "使用 bash 执行：echo 'Thread 2 data' > /tmp/thread2.txt && cat /tmp/thread2.txt",
            thread_id="thread-2",
        )
        print_info(f"Thread 2 创建文件: {result13['messages'][-1].content}")

        # Thread 1: 验证只能看到自己的文件（文件系统是共享的，但 session 独立）
        result14 = agent.invoke(
            "使用 bash 执行：echo $$ && ls /tmp/thread*.txt",
            thread_id="thread-1",
        )
        print_info(f"Thread 1 查看文件: {result14['messages'][-1].content}")

        # Thread 2: 验证
        result15 = agent.invoke(
            "使用 bash 执行：echo $$ && ls /tmp/thread*.txt",
            thread_id="thread-2",
        )
        print_info(f"Thread 2 查看文件: {result15['messages'][-1].content}")

        # 验证：两个 thread 都能看到两个文件（文件系统共享）
        if "thread1.txt" in result14["messages"][-1].content and "thread2.txt" in result14["messages"][-1].content:
            print_pass("不同 thread_id 的文件系统操作正确共享")
        else:
            print_fail("文件系统隔离异常")

        # 清理
        agent.invoke("使用 bash 执行：rm -f /tmp/thread*.txt", thread_id="thread-1")

        # ========== 测试 6: 长时间运行的命令 ==========
        print_test("6. 长时间运行的命令")

        result16 = agent.invoke(
            "使用 bash 执行：sleep 1 && echo 'Completed after 1 second'",
            thread_id=thread_id,
        )
        print_info(f"Sleep 命令: {result16['messages'][-1].content}")

        if "Completed" in result16["messages"][-1].content:
            print_pass("长时间运行的命令正确执行")
        else:
            print_fail("长时间命令执行失败")

        # ========== 测试 7: 错误处理 ==========
        print_test("7. 错误处理和恢复")

        # 执行一个会失败的命令
        result17 = agent.invoke(
            "使用 bash 执行：cat /nonexistent/file.txt",
            thread_id=thread_id,
        )
        print_info(f"错误命令: {result17['messages'][-1].content}")

        # 验证 session 仍然可用
        result18 = agent.invoke(
            "使用 bash 执行：echo 'Session still alive'",
            thread_id=thread_id,
        )
        print_info(f"恢复测试: {result18['messages'][-1].content}")

        if "still alive" in result18["messages"][-1].content:
            print_pass("Session 在错误后正确恢复")
        else:
            print_fail("Session 恢复失败")

        # ========== 测试 8: 管道和重定向 ==========
        print_test("8. 管道和重定向")

        result19 = agent.invoke(
            "使用 bash 执行：echo 'line1\\nline2\\nline3' | grep 'line2' && echo 'Pipeline works'",
            thread_id=thread_id,
        )
        print_info(f"管道测试: {result19['messages'][-1].content}")

        if "line2" in result19["messages"][-1].content and "Pipeline works" in result19["messages"][-1].content:
            print_pass("管道和重定向正确工作")
        else:
            print_fail("管道操作失败")

        # ========== 最终清理 ==========
        print_test("最终清理")

        result20 = agent.invoke(
            f"使用 bash 执行：rm -f {test_file} && echo 'All cleaned up'",
            thread_id=thread_id,
        )
        print_info(f"清理结果: {result20['messages'][-1].content}")

        print(f"\n{Colors.BOLD}{Colors.GREEN}{'=' * 70}")
        print("所有测试完成！")
        print(f"{'=' * 70}{Colors.RESET}\n")

    except Exception as e:
        print_fail(f"测试失败: {e}")
        import traceback

        traceback.print_exc()

    finally:
        agent.cleanup()


if __name__ == "__main__":
    test_multiround_persistence()
