"""Argument parsing and command dispatch for the Stage-1 agent CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from .client import AgentCliClient
from .config import load_cli_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mycel-agent", description="Stage-1 external agent CLI for Mycel chat")
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--agent-user-id")
    shared.add_argument("--profile")
    shared.add_argument("--chat-base-url")
    shared.add_argument("--threads-base-url")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("whoami", parents=[shared])

    chats = sub.add_parser("chats", parents=[shared])
    chats_sub = chats.add_subparsers(dest="chats_command", required=True)
    chats_sub.add_parser("list", parents=[shared])

    messages = sub.add_parser("messages", parents=[shared])
    messages_sub = messages.add_subparsers(dest="messages_command", required=True)
    messages_list = messages_sub.add_parser("list", parents=[shared])
    messages_list.add_argument("chat_id")
    messages_list.add_argument("--limit", type=int, default=50)
    messages_list.add_argument("--before")
    messages_unread = messages_sub.add_parser("unread", parents=[shared])
    messages_unread.add_argument("chat_id")

    read = sub.add_parser("read", parents=[shared])
    read.add_argument("chat_id")

    send = sub.add_parser("send", parents=[shared])
    send.add_argument("chat_id")
    send.add_argument("content")
    send.add_argument("--reply-to")
    send.add_argument("--mention", action="append", dest="mentions")
    send.add_argument("--signal")
    send.add_argument("--no-enforce-caught-up", action="store_true")

    direct = sub.add_parser("direct", parents=[shared])
    direct.add_argument("target_id")

    external = sub.add_parser("external", parents=[shared])
    external_sub = external.add_subparsers(dest="external_command", required=True)
    external_create = external_sub.add_parser("create", parents=[shared])
    external_create.add_argument("user_id")
    external_create.add_argument("display_name")
    external_sub.add_parser("list", parents=[shared])

    return parser


def run_cli(
    argv: Sequence[str],
    *,
    messaging_client: Any | None = None,
    identity_client: Any | None = None,
    runtime_read_client: Any | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv))
    out = stdout or sys.stdout

    cfg = load_cli_config(
        agent_user_id=args.agent_user_id,
        agent_alias=getattr(args, "profile", None),
        chat_base_url=args.chat_base_url,
        threads_base_url=args.threads_base_url,
    )
    default_client = AgentCliClient.from_config(cfg)
    client = AgentCliClient(
        messaging=messaging_client or default_client.messaging,
        identity=identity_client or default_client.identity,
        runtime_read=runtime_read_client or default_client.runtime_read,
        agent_user_id=cfg.agent_user_id,
    )

    if args.command == "whoami":
        payload = client.whoami()
    elif args.command == "chats":
        payload = client.list_chats()
    elif args.command == "messages" and args.messages_command == "list":
        payload = client.list_messages(args.chat_id, limit=args.limit, before=args.before)
    elif args.command == "messages" and args.messages_command == "unread":
        payload = client.list_unread(args.chat_id)
    elif args.command == "read":
        payload = client.mark_read(args.chat_id)
    elif args.command == "send":
        payload = client.send(
            args.chat_id,
            args.content,
            reply_to=args.reply_to,
            mentions=args.mentions,
            signal=args.signal,
            enforce_caught_up=not args.no_enforce_caught_up,
        )
    elif args.command == "direct":
        payload = client.direct(args.target_id)
    elif args.command == "external" and args.external_command == "create":
        payload = client.create_external_user(user_id=args.user_id, display_name=args.display_name)
    elif args.command == "external" and args.external_command == "list":
        payload = client.list_external_users()
    else:
        raise RuntimeError(f"unsupported command: {args.command}")

    out.write(json.dumps(payload, ensure_ascii=False))
    out.write("\n")
    return 0
