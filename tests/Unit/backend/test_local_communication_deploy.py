from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = ROOT / "deploy/local-communication/compose.yml"
GATEWAY_PATH = ROOT / "deploy/local-communication/rest-gateway.conf"
SCHEMA_PATH = ROOT / "storage/schema/local_communication.sql"


def test_local_communication_compose_is_self_contained() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text())

    assert "networks" not in compose
    assert set(compose["services"]) == {"db", "postgrest", "supabase-rest", "backend"}
    assert compose["services"]["backend"]["environment"]["MYCEL_RUNTIME_PROFILE"] == "communication"
    assert compose["services"]["backend"]["environment"]["SUPABASE_INTERNAL_URL"] == "http://supabase-rest:8000"
    assert compose["services"]["backend"]["environment"]["LEON_SUPABASE_CLIENT_FACTORY"] == (
        "backend.identity.auth.supabase_runtime:create_supabase_client"
    )


def test_local_communication_rest_gateway_preserves_supabase_rest_shape() -> None:
    gateway = GATEWAY_PATH.read_text()

    assert "location /rest/v1/" in gateway
    assert "proxy_pass http://postgrest:3000/" in gateway
    assert 'return 404 "local communication profile exposes only /rest/v1\\n";' in gateway


def test_local_communication_schema_contains_runtime_primitives() -> None:
    sql = SCHEMA_PATH.read_text()

    required_fragments = [
        "create role anon nologin",
        "create role authenticated nologin",
        "create role service_role nologin bypassrls",
        "create table if not exists identity.users",
        "is_guest boolean not null default false",
        "check (type = 'human' or is_guest = false)",
        "create table if not exists chat.chats",
        "create table if not exists chat.chat_members",
        "create table if not exists chat.messages",
        "create table if not exists chat.workflow_state",
        "create table if not exists chat.tasks",
        "create table if not exists chat.workflow_events",
        "create table if not exists agent.message_queue",
        "create or replace function chat.increment_chat_message_seq",
        "create or replace function identity.increment_user_thread_seq",
        "grant execute on all functions in schema identity, chat",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in sql]

    assert missing == []
    assert "owner_profile" not in sql
