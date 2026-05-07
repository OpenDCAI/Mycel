from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "storage/schema/local_communication.sql"
CLI_MINIMAL_COMPOSE = ROOT / "deploy/cli-minimal/compose.yml"
CLI_MINIMAL_GATEWAY_CONF = ROOT / "deploy/cli-minimal/rest-gateway.conf"


def _compose_files() -> list[Path]:
    return sorted((ROOT / "deploy").glob("**/compose*.yml")) + sorted((ROOT / "deploy").glob("**/docker-compose*.yml"))


def test_active_deploys_do_not_mount_handwritten_local_communication_schema() -> None:
    offenders: list[str] = []
    for path in _compose_files():
        compose = yaml.safe_load(path.read_text()) or {}
        for service_name, service in (compose.get("services") or {}).items():
            for volume in service.get("volumes") or []:
                if "local_communication.sql" in str(volume):
                    offenders.append(f"{path.relative_to(ROOT)}:{service_name}:{volume}")

    assert offenders == []


def test_local_communication_schema_is_not_a_product_bootstrap_source() -> None:
    assert not SCHEMA_PATH.exists()


def test_cli_minimal_compose_is_four_long_running_services_plus_schema_init() -> None:
    compose = yaml.safe_load(CLI_MINIMAL_COMPOSE.read_text()) or {}
    services = compose.get("services") or {}

    assert set(services) == {"postgres", "schema-init", "postgrest", "gateway", "mycel-backend"}
    assert services["schema-init"]["restart"] == "no"
    assert services["schema-init"]["command"] == [
        "python",
        "scripts/apply_app_schema.py",
        "--prepare-supabase-roles",
        "--database-url",
        "postgresql://postgres:postgres@postgres:5432/postgres",
    ]
    assert "local_communication.sql" not in CLI_MINIMAL_COMPOSE.read_text()


def test_cli_minimal_backend_uses_communication_profile_and_thin_gateway() -> None:
    compose = yaml.safe_load(CLI_MINIMAL_COMPOSE.read_text()) or {}
    backend_env = compose["services"]["mycel-backend"]["environment"]
    backend_ports = compose["services"]["mycel-backend"]["ports"]
    postgrest_env = compose["services"]["postgrest"]["environment"]

    assert backend_ports == ["${MYCEL_BIND_HOST:-127.0.0.1}:${MYCEL_PORT:-8042}:8900"]
    assert backend_env["MYCEL_RUNTIME_PROFILE"] == "communication"
    assert backend_env["LEON_STORAGE_STRATEGY"] == "supabase"
    assert backend_env["LEON_SUPABASE_CLIENT_FACTORY"] == "backend.identity.auth.supabase_runtime:create_supabase_client"
    assert backend_env["SUPABASE_INTERNAL_URL"] == "http://gateway:8000"
    assert backend_env["SUPABASE_PUBLIC_URL"] == "${MYCEL_PUBLIC_URL:-http://127.0.0.1:8042}"
    assert backend_env["LEON_DB_SCHEMA"] == "identity"
    assert backend_env["LEON_POSTGRES_URL"] == "postgresql://postgres:postgres@postgres:5432/postgres"
    assert postgrest_env["PGRST_DB_SCHEMAS"] == "identity,chat,agent,container,library,observability"
    assert postgrest_env["PGRST_JWT_SECRET"] == "${SUPABASE_JWT_SECRET:?SUPABASE_JWT_SECRET is required}"
    assert backend_env["SUPABASE_JWT_SECRET"] == "${SUPABASE_JWT_SECRET:?SUPABASE_JWT_SECRET is required}"


def test_cli_minimal_gateway_is_nginx_rest_only_not_supabase_bundle() -> None:
    compose = yaml.safe_load(CLI_MINIMAL_COMPOSE.read_text()) or {}
    services = compose.get("services") or {}
    gateway = services["gateway"]
    gateway_conf = CLI_MINIMAL_GATEWAY_CONF.read_text()

    assert gateway["image"] == "nginx:1.27-alpine"
    assert "postgrest:3000" in gateway_conf
    assert "/rest/v1/" in gateway_conf
    assert "/auth/v1/" not in gateway_conf
    assert not {"gotrue", "studio", "realtime", "storage", "analytics", "kong"} & set(services)
