"""
run_id_demo.py — 验证 LangGraph 中 run_id 的完整链路

验证链路：configurable.run_id → node 读取 → 注入消息 metadata → checkpoint 持久化 → 历史加载后 metadata 保留

运行：uv run python examples/run_id_demo.py
"""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph


def build_graph(checkpointer=None):
    """构建最简 graph，node 从 configurable 读 run_id 并注入消息 metadata。"""

    def my_node(state: MessagesState, config: RunnableConfig) -> dict:
        run_id = config.get("configurable", {}).get("run_id")
        ai_msg = AIMessage(
            content=f"response for run {run_id}",
            metadata={"run_id": run_id} if run_id else {},
        )
        return {"messages": [ai_msg]}

    graph = StateGraph(MessagesState)
    graph.add_node("my_node", my_node)
    graph.add_edge(START, "my_node")
    graph.add_edge("my_node", END)
    return graph.compile(checkpointer=checkpointer)


def test_basic_passthrough():
    """验证 configurable.run_id 在 node 中可读、注入 metadata 后 invoke 返回保留。"""
    print("── 1. 基础：configurable → node → metadata ──")

    compiled = build_graph()
    run_id = str(uuid.uuid4())
    result = compiled.invoke(
        {"messages": [HumanMessage(content="hello")]},
        config={"configurable": {"thread_id": "t1", "run_id": run_id}},
    )

    last_msg = result["messages"][-1]
    assert last_msg.metadata.get("run_id") == run_id
    print(f"[PASS] metadata['run_id'] = {run_id}")


def test_checkpoint_persistence():
    """验证 metadata.run_id 经过 checkpoint 持久化后，从历史加载仍然存在。"""
    print("\n── 2. 持久化：checkpoint → 历史加载 → metadata 保留 ──")

    checkpointer = MemorySaver()
    compiled = build_graph(checkpointer=checkpointer)
    thread_id = "persistence-test"

    # Turn 1
    run_id_1 = str(uuid.uuid4())
    compiled.invoke(
        {"messages": [HumanMessage(content="turn 1")]},
        config={"configurable": {"thread_id": thread_id, "run_id": run_id_1}},
    )

    # Turn 2（同一 thread，不同 run_id）
    run_id_2 = str(uuid.uuid4())
    compiled.invoke(
        {"messages": [HumanMessage(content="turn 2")]},
        config={"configurable": {"thread_id": thread_id, "run_id": run_id_2}},
    )

    # 从 checkpoint 加载历史（模拟刷新页面后重新加载）
    state = compiled.get_state({"configurable": {"thread_id": thread_id}})
    messages = state.values["messages"]

    # 预期：4 条消息（Human1, AI1, Human2, AI2）
    assert len(messages) == 4, f"预期 4 条消息，实际 {len(messages)}"

    # 检查 AI 消息的 metadata.run_id 是否保留
    ai_msg_1 = messages[1]  # 第一轮 AI 回复
    ai_msg_2 = messages[3]  # 第二轮 AI 回复

    assert ai_msg_1.metadata.get("run_id") == run_id_1, f"Turn 1 metadata 丢失: {ai_msg_1.metadata}"
    assert ai_msg_2.metadata.get("run_id") == run_id_2, f"Turn 2 metadata 丢失: {ai_msg_2.metadata}"
    assert run_id_1 != run_id_2, "两轮 run_id 应该不同"

    print(f"[PASS] Turn 1 AI metadata['run_id'] = {run_id_1}")
    print(f"[PASS] Turn 2 AI metadata['run_id'] = {run_id_2}")
    print("[PASS] checkpoint 持久化后 metadata.run_id 保留完好，可用于 Turn 分组")


def main() -> None:
    test_basic_passthrough()
    test_checkpoint_persistence()
    print("\n结论：configurable.run_id → node → metadata → checkpoint → 历史加载，全链路可行。")


if __name__ == "__main__":
    main()
