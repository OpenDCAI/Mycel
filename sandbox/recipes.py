from __future__ import annotations

import shlex
from copy import deepcopy
from typing import Any

FEATURE_CATALOG: dict[str, dict[str, str]] = {
    "lark_cli": {
        "key": "lark_cli",
        "name": "Lark CLI",
        "description": "在 sandbox 初始化时懒安装并校验。",
        "icon": "feishu",
    },
}


def provider_type_from_name(name: str) -> str:
    if name.startswith("daytona"):
        return "daytona"
    if name.startswith("docker"):
        return "docker"
    if name.startswith("e2b"):
        return "e2b"
    if name.startswith("agentbay"):
        return "agentbay"
    return "local"


def humanize_recipe_provider(name: str) -> str:
    return " ".join(part[:1].upper() + part[1:] for part in name.replace("-", "_").split("_") if part)


def default_recipe_id(provider_name: str) -> str:
    return f"{provider_name}:default"


def default_recipe_name(provider_name: str) -> str:
    return f"{humanize_recipe_provider(provider_name)} Default"


def default_recipe_snapshot(provider_type: str, *, provider_name: str | None = None) -> dict[str, Any]:
    provider_name = provider_name or provider_type
    return {
        "id": default_recipe_id(provider_name),
        "name": default_recipe_name(provider_name),
        "desc": f"Default recipe for {provider_name}",
        "provider_name": provider_name,
        "provider_type": provider_type,
        "features": {"lark_cli": False},
        "configurable_features": {"lark_cli": True},
        "feature_options": [deepcopy(FEATURE_CATALOG["lark_cli"])],
        "builtin": True,
    }


def normalize_recipe_snapshot(
    provider_type: str,
    recipe: dict[str, Any] | None = None,
    *,
    provider_name: str | None = None,
) -> dict[str, Any]:
    if recipe is not None and provider_name is None:
        raw_provider_name = recipe.get("provider_name")
        if isinstance(raw_provider_name, str) and raw_provider_name.strip():
            provider_name = raw_provider_name.strip()
    base = default_recipe_snapshot(provider_type, provider_name=provider_name)
    if recipe is None:
        return base

    requested_type = str(recipe.get("provider_type") or provider_type).strip() or provider_type
    if requested_type != provider_type:
        raise RuntimeError(f"Recipe provider_type {requested_type!r} does not match selected provider_type {provider_type!r}")

    requested_features = recipe.get("features")
    normalized_features = dict(base["features"])
    if isinstance(requested_features, dict):
        for key, value in requested_features.items():
            if key in FEATURE_CATALOG:
                normalized_features[key] = bool(value)

    builtin = recipe.get("builtin", base["builtin"])
    if builtin is None:
        builtin = base["builtin"]

    return {
        **base,
        "id": str(recipe.get("id") or base["id"]),
        "name": str(recipe.get("name") or base["name"]),
        "desc": str(recipe.get("desc") or base["desc"]),
        "provider_name": str(recipe.get("provider_name") or base["provider_name"]),
        "features": normalized_features,
        "builtin": bool(builtin),
    }


def recipe_features(recipe: dict[str, Any] | None) -> dict[str, bool]:
    if not recipe:
        return {}
    raw = recipe.get("features")
    if not isinstance(raw, dict):
        return {}
    return {key: bool(value) for key, value in raw.items() if key in FEATURE_CATALOG}


def list_builtin_recipes(sandbox_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    providers_by_name: dict[str, dict[str, Any]] = {}
    for sandbox in sandbox_types:
        provider_name = str(sandbox["name"])
        if not provider_name or provider_name in providers_by_name:
            continue
        providers_by_name[provider_name] = sandbox

    for provider_name, sandbox in providers_by_name.items():
        provider_type = str(sandbox.get("provider") or provider_type_from_name(provider_name))
        available = bool(sandbox.get("available", False))
        item = default_recipe_snapshot(provider_type, provider_name=provider_name)
        items.append(
            {
                **item,
                "provider_name": provider_name,
                "provider_type": provider_type,
                "type": "recipe",
                "available": available,
                "created_at": 0,
                "updated_at": 0,
            }
        )
    return items


def resolve_builtin_recipe(provider_type: str, recipe_id: str | None = None) -> dict[str, Any]:
    base = default_recipe_snapshot(provider_type)
    if recipe_id and recipe_id != base["id"]:
        raise RuntimeError(f"Unknown recipe id {recipe_id!r} for provider type {provider_type}. Builtin recipes only expose defaults.")
    return base


def bootstrap_recipe(provider, *, session_id: str, recipe: dict[str, Any] | None) -> dict[str, str]:
    features = recipe_features(recipe)
    if not features.get("lark_cli"):
        return {}

    cwd = _resolve_recipe_cwd(provider)
    home_dir = _resolve_recipe_home(provider)
    user_local_bin = f"{home_dir}/.local/bin"
    base_path = provider.execute(session_id, 'printf %s "$PATH"', timeout_ms=10_000, cwd=cwd).output.strip()
    desired_path = _prepend_path(user_local_bin, base_path)

    verify = provider.execute(
        session_id,
        f"export PATH={shlex.quote(desired_path)}\ncommand -v lark-cli",
        timeout_ms=10_000,
        cwd=cwd,
    )
    if verify.exit_code == 0:
        _install_lark_cli_wrapper(
            provider,
            session_id=session_id,
            cwd=cwd,
            home_dir=home_dir,
            user_local_bin=user_local_bin,
        )
        return {"PATH": desired_path}

    # @@@recipe-bootstrap-lark-cli - Bootstrap must install into a user-writable prefix and persist PATH into
    # terminal env_delta, otherwise remote sandboxes like self-hosted Daytona hit EACCES on global npm installs.
    install = provider.execute(
        session_id,
        "\n".join(
            [
                f"mkdir -p {shlex.quote(user_local_bin)}",
                f"export NPM_CONFIG_PREFIX={shlex.quote(f'{home_dir}/.local')}",
                f"export PATH={shlex.quote(desired_path)}",
                "npm install -g @larksuite/cli",
                "command -v lark-cli",
            ]
        ),
        timeout_ms=300_000,
        cwd=cwd,
    )
    if install.exit_code != 0:
        recipe_name = recipe.get("name") if isinstance(recipe, dict) else None
        error = install.error or install.output or "unknown bootstrap error"
        raise RuntimeError(f"Recipe bootstrap failed for {recipe_name or 'unknown recipe'}: {error}")

    _install_lark_cli_wrapper(
        provider,
        session_id=session_id,
        cwd=cwd,
        home_dir=home_dir,
        user_local_bin=user_local_bin,
    )
    return {"PATH": desired_path}


def _resolve_recipe_cwd(provider) -> str:
    for attr in ("default_cwd", "default_context_path", "mount_path"):
        val = getattr(provider, attr, None)
        if isinstance(val, str) and val:
            return val
    return "/home/user"


def _resolve_recipe_home(provider) -> str:
    cwd = _resolve_recipe_cwd(provider)
    if cwd.startswith("/home/"):
        parts = cwd.split("/")
        if len(parts) >= 3 and parts[2]:
            return f"/home/{parts[2]}"
    return "/home/user"


def _prepend_path(path_entry: str, current_path: str) -> str:
    parts = [item for item in current_path.split(":") if item]
    if path_entry in parts:
        return current_path or path_entry
    return ":".join([path_entry, *parts]) if parts else path_entry


def _install_lark_cli_wrapper(provider, *, session_id: str, cwd: str, home_dir: str, user_local_bin: str) -> None:
    wrapper_path = f"{user_local_bin}/lark-cli"
    real_bin = f"{home_dir}/.local/lib/node_modules/@larksuite/cli/bin/lark-cli"
    # @@@lark-cli-pty-ci-wrapper - The upstream binary hangs under Daytona PTY unless CI=1.
    # Install a tiny wrapper so agent Bash calls keep using `lark-cli`, but run the real binary
    # with the minimal env tweak that makes PTY execution terminate.
    script = "\n".join(
        [
            "#!/bin/sh",
            f'exec env CI=1 {shlex.quote(real_bin)} "$@"',
        ]
    )
    cmd = "\n".join(
        [
            f"mkdir -p {shlex.quote(user_local_bin)}",
            f"cat <<'EOF' > {shlex.quote(wrapper_path)}",
            script,
            "EOF",
            f"chmod +x {shlex.quote(wrapper_path)}",
            f"export PATH={shlex.quote(user_local_bin)}:$PATH",
            "lark-cli --version",
        ]
    )
    result = provider.execute(session_id, cmd, timeout_ms=60_000, cwd=cwd)
    if result.exit_code != 0:
        error = result.error or result.output or "failed to install lark-cli wrapper"
        raise RuntimeError(f"Recipe bootstrap failed while installing lark-cli wrapper: {error}")
