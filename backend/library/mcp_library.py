"""File-backed MCP library store."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.library.paths import LIBRARY_DIR

_MCP_META_KEYS = {"desc", "category", "created_at", "updated_at", "name"}


def list_items() -> list[dict[str, Any]]:
    data = _read_data()
    return [_resource_item(name, cfg, name=name) for name, cfg in data.get("mcpServers", {}).items()]


def create(name: str, desc: str = "", category: str = "") -> dict[str, Any]:
    now = int(time.time() * 1000)
    data = _read_data()
    meta = {
        "desc": desc,
        "category": category or "未分类",
        "created_at": now,
        "updated_at": now,
    }
    data["mcpServers"][name] = meta
    _write_data(data)
    return _resource_item(name, meta, name=name)


def update(resource_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    data = _read_data()
    servers = data.get("mcpServers", {})
    if resource_id not in servers:
        return None
    now = int(time.time() * 1000)
    servers[resource_id].update(updates)
    servers[resource_id]["updated_at"] = now
    _write_data(data)
    entry = servers[resource_id]
    return _resource_item(resource_id, entry, name=entry.get("name", resource_id), updated_at=now)


def delete(resource_id: str) -> bool:
    data = _read_data()
    servers = data.get("mcpServers", {})
    if resource_id not in servers:
        return False
    del servers[resource_id]
    _write_data(data)
    return True


def get_config_by_name(name: str) -> dict[str, Any] | None:
    cfg = _read_data().get("mcpServers", {}).get(name)
    if cfg is None:
        return None
    if not isinstance(cfg, dict):
        raise RuntimeError(f"Library MCP config must be a JSON object: {name}")
    return {key: value for key, value in cfg.items() if key not in _MCP_META_KEYS}


def get_content(resource_id: str) -> str | None:
    config = get_config_by_name(resource_id)
    if config is None:
        return None
    if not config:
        config = {"command": "", "args": [], "env": {}}
    return json.dumps(config, ensure_ascii=False, indent=2)


def update_content(resource_id: str, content: str) -> bool:
    data = _read_data()
    servers = data.get("mcpServers", {})
    if resource_id not in servers:
        return False
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Library MCP content must be valid JSON: {resource_id}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Library MCP content must be a JSON object: {resource_id}")
    now = int(time.time() * 1000)
    existing = servers[resource_id]
    preserved = {key: existing[key] for key in _MCP_META_KEYS if key in existing and key != "updated_at"}
    servers[resource_id] = {**parsed, **preserved, "updated_at": now}
    _write_data(data)
    return True


def _read_data() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"mcpServers": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"Library MCP file must be a JSON object: {path}")
    servers = raw.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise RuntimeError(f"Library MCP mcpServers must be a JSON object: {path}")
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            raise RuntimeError(f"Library MCP server config must be a JSON object: {path}#{name}")
    return raw


def _write_data(data: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _path() -> Path:
    return LIBRARY_DIR / ".mcp.json"


def _resource_item(resource_id: str, meta: dict[str, Any], *, name: str, updated_at: int | None = None) -> dict[str, Any]:
    return {
        "id": resource_id,
        "type": "mcp",
        "name": name,
        "desc": meta.get("desc", ""),
        "created_at": meta.get("created_at", 0),
        "updated_at": updated_at if updated_at is not None else meta.get("updated_at", 0),
    }
