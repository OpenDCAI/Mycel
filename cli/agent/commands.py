"""Argument parsing and command dispatch for the Stage-1 agent CLI."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from .client import AgentCliClient
from .config import DEFAULT_APP_BASE_URL, load_cli_config, load_profiles, save_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mycel-agent", description="Stage-1 external agent CLI for Mycel chat")
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--agent-user-id")
    shared.add_argument("--profile")
    shared.add_argument("--chat-base-url")
    shared.add_argument("--threads-base-url")
    shared.add_argument("--app-base-url")
    shared.add_argument("--auth-token")

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

    profile = sub.add_parser("profile", parents=[shared])
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    profile_set = profile_sub.add_parser("set", parents=[shared])
    profile_set.add_argument("name")
    profile_sub.add_parser("list", parents=[shared])

    auth = sub.add_parser("auth", parents=[shared])
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_send_otp = auth_sub.add_parser("send-otp", parents=[shared])
    auth_send_otp.add_argument("email")
    auth_send_otp.add_argument("invite_code")
    auth_send_otp.add_argument("--password-stdin", action="store_true")
    auth_verify_otp = auth_sub.add_parser("verify-otp", parents=[shared])
    auth_verify_otp.add_argument("email")
    auth_verify_otp.add_argument("token")
    auth_complete_register = auth_sub.add_parser("complete-register", parents=[shared])
    auth_complete_register.add_argument("invite_code")
    auth_complete_register.add_argument("--temp-token-stdin", action="store_true")
    auth_login = auth_sub.add_parser("login", parents=[shared])
    auth_login.add_argument("identifier")
    auth_login.add_argument("--password-stdin", action="store_true")

    agents = sub.add_parser("agents", parents=[shared])
    agents_sub = agents.add_subparsers(dest="agents_command", required=True)
    agents_sub.add_parser("list", parents=[shared])
    agents_create = agents_sub.add_parser("create", parents=[shared])
    agents_create.add_argument("name")
    agents_create.add_argument("--description", default="")

    return parser


def _requires_agent_identity(args: argparse.Namespace) -> bool:
    if args.command in {"whoami", "read", "send", "direct"}:
        return True
    if args.command == "chats":
        return True
    if args.command == "messages":
        return True
    return False


def _resolve_login_password(args: argparse.Namespace, stdin: TextIO) -> str:
    if args.password_stdin:
        password = stdin.readline().rstrip("\r\n")
        if not password:
            raise RuntimeError("stdin password is required")
        return password
    return getpass.getpass("Password: ")


def _resolve_temp_token(args: argparse.Namespace, stdin: TextIO) -> str:
    if args.temp_token_stdin:
        temp_token = stdin.readline().rstrip("\r\n")
        if not temp_token:
            raise RuntimeError("stdin temp token is required")
        return temp_token
    return getpass.getpass("Temp token: ")


def run_cli(
    argv: Sequence[str],
    *,
    messaging_client: Any | None = None,
    identity_client: Any | None = None,
    runtime_read_client: Any | None = None,
    auth_client: Any | None = None,
    panel_client: Any | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv))
    in_stream = stdin or sys.stdin
    out = stdout or sys.stdout

    cfg = load_cli_config(
        agent_user_id=args.agent_user_id,
        agent_alias=getattr(args, "profile", None),
        chat_base_url=args.chat_base_url,
        threads_base_url=args.threads_base_url,
        app_base_url=args.app_base_url,
        auth_token=args.auth_token,
        require_agent_user_id=_requires_agent_identity(args),
    )
    default_client = AgentCliClient.from_config(cfg)
    client = AgentCliClient(
        messaging=messaging_client or default_client.messaging,
        identity=identity_client or default_client.identity,
        runtime_read=runtime_read_client or default_client.runtime_read,
        auth=auth_client or default_client.auth,
        panel=panel_client or default_client.panel,
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
    elif args.command == "profile" and args.profile_command == "set":
        saved_app_base_url = None
        if args.app_base_url or cfg.auth_token or cfg.app_base_url != DEFAULT_APP_BASE_URL:
            saved_app_base_url = cfg.app_base_url
        payload = save_profile(
            name=args.name,
            agent_user_id=cfg.agent_user_id,
            chat_base_url=cfg.chat_base_url,
            threads_base_url=cfg.threads_base_url,
            app_base_url=saved_app_base_url,
            auth_token=cfg.auth_token,
        )
    elif args.command == "profile" and args.profile_command == "list":
        payload = [{"name": name, **profile} for name, profile in sorted(load_profiles().items())]
    elif args.command == "auth" and args.auth_command == "send-otp":
        payload = client.send_otp(args.email, _resolve_login_password(args, in_stream), args.invite_code)
    elif args.command == "auth" and args.auth_command == "verify-otp":
        payload = client.verify_otp(args.email, args.token)
    elif args.command == "auth" and args.auth_command == "complete-register":
        payload = client.complete_register(_resolve_temp_token(args, in_stream), args.invite_code)
    elif args.command == "auth" and args.auth_command == "login":
        payload = client.login(args.identifier, _resolve_login_password(args, in_stream))
    elif args.command == "agents" and args.agents_command == "list":
        payload = client.list_agents()
    elif args.command == "agents" and args.agents_command == "create":
        payload = client.create_agent(args.name, description=args.description)
    else:
        raise RuntimeError(f"unsupported command: {args.command}")

    out.write(json.dumps(payload, ensure_ascii=False))
    out.write("\n")
    return 0
