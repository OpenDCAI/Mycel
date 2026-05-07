from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "storage/schema/local_communication.sql"


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
