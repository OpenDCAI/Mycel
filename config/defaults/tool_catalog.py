"""Tool catalog — single source of truth for all available agent tools.

Each entry is a ToolDef with fully-typed fields.  The catalog is the
authoritative registry consumed by agent_user_service to build tool lists
for the panel UI.

Adding a new tool:  append an entry below.
Changing a default: set `default=False` (tool appears in panel but off).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ToolGroup(StrEnum):
    FILESYSTEM = "filesystem"
    SEARCH = "search"
    COMMAND = "command"
    WEB = "web"
    AGENT = "agent"
    CHAT = "chat"
    TODO = "todo"
    SKILLS = "skills"
    SYSTEM = "system"


class ToolMode(StrEnum):
    INLINE = "inline"
    DEFERRED = "deferred"


class ToolDef(BaseModel):
    """Definition of a single tool available in the agent tool catalog."""

    name: str
    desc: str
    group: ToolGroup
    mode: ToolMode = ToolMode.INLINE
    default: bool = True  # False -> off by default in new agent configs


# ── Catalog ────────────────────────────────────────────────────────────────

TOOLS: list[ToolDef] = [
    # filesystem
    ToolDef(name="Read", desc="读取文件内容", group=ToolGroup.FILESYSTEM),
    ToolDef(name="Write", desc="写入文件", group=ToolGroup.FILESYSTEM),
    ToolDef(name="Edit", desc="编辑文件（精确替换）", group=ToolGroup.FILESYSTEM),
    ToolDef(name="list_dir", desc="列出目录内容", group=ToolGroup.FILESYSTEM),
    # search
    ToolDef(name="Grep", desc="正则搜索文件内容（基于 ripgrep）", group=ToolGroup.SEARCH),
    ToolDef(name="Glob", desc="按 glob 模式查找文件", group=ToolGroup.SEARCH),
    # command
    ToolDef(name="Bash", desc="执行 Shell 命令", group=ToolGroup.COMMAND),
    # web
    ToolDef(name="WebSearch", desc="搜索互联网", group=ToolGroup.WEB),
    ToolDef(name="WebFetch", desc="获取网页内容并 AI 提取信息", group=ToolGroup.WEB),
    # agent
    ToolDef(name="TaskOutput", desc="获取后台任务输出", group=ToolGroup.AGENT),
    ToolDef(name="TaskStop", desc="停止后台任务", group=ToolGroup.AGENT),
    ToolDef(name="Agent", desc="启动子 Agent 执行任务", group=ToolGroup.AGENT),
    ToolDef(name="SendMessage", desc="向运行中的 Agent 发送排队消息", group=ToolGroup.AGENT),
    # chat
    ToolDef(name="list_chats", desc="列出当前实体可访问的聊天会话", group=ToolGroup.CHAT),
    ToolDef(name="read_messages", desc="读取聊天消息并标记为已读", group=ToolGroup.CHAT),
    ToolDef(name="send_message", desc="向聊天对象发送消息", group=ToolGroup.CHAT),
    ToolDef(name="search_messages", desc="搜索历史聊天消息", group=ToolGroup.CHAT),
    # todo
    ToolDef(name="TaskCreate", desc="创建待办任务", group=ToolGroup.TODO, mode=ToolMode.DEFERRED),
    ToolDef(name="TaskGet", desc="获取任务详情", group=ToolGroup.TODO, mode=ToolMode.DEFERRED),
    ToolDef(name="TaskList", desc="列出所有任务", group=ToolGroup.TODO, mode=ToolMode.DEFERRED),
    ToolDef(name="TaskUpdate", desc="更新任务状态", group=ToolGroup.TODO, mode=ToolMode.DEFERRED),
    # skills
    ToolDef(name="load_skill", desc="加载 Skill", group=ToolGroup.SKILLS),
    # system
    ToolDef(name="tool_search", desc="搜索可用工具", group=ToolGroup.SYSTEM),
    ToolDef(name="LSP", desc="Language Server Protocol 操作", group=ToolGroup.SYSTEM, mode=ToolMode.DEFERRED, default=False),
]

# Fast lookup: name → ToolDef
TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}
