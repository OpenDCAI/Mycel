#!/usr/bin/env python3
"""Backend tidy layout checker.

Enforces the target backend/ layout defined in
program/doc/core/backend-package-dependencies-2026-04-20.md §3 (Target layout).

Run from repo root:
    python scripts/tidy/check_backend_layout.py

Exit code 0 = layout matches target. Non-zero = violations listed on stdout.

Invariants checked:

1. Forbidden prefixes: backend/ root must not contain sandbox_*, auth_*,
   avatar_*, resource_*, user_sandbox_*, user_resource_*, supabase_runtime*,
   local_workspace*, profile.py, contact_bootstrap.py, recipe_bootstrap.py,
   virtual_threads.py, message_content.py, event_bus.py, file_channel.py,
   display_builder.py, library_paths.py, versioning.py,
   agent_user_snapshot_apply.py, app_entrypoint.py, request_app.py,
   runtime_storage_bootstrap.py, storage_container_cache.py.

2. Forbidden directories at backend/ root: utils/, common/, shared/, helpers/,
   thread_runtime/, agent_runtime/, protocols/ (moved to top-level).

3. Forbidden directories: backend/web/services/ must not exist.

4. Required top-level directories: protocols/, core/, sandbox/, storage/,
   messaging/, config/.

5. Required backend subdirectories: web/, chat/, identity/, threads/,
   sandboxes/, library/, hub/, monitor/, bootstrap/.

6. Required sub-sub-packages: backend/identity/auth/, backend/identity/avatar/,
   backend/sandboxes/runtime/, backend/sandboxes/resources/,
   backend/threads/chat_adapters/, backend/threads/display/,
   backend/threads/events/, backend/threads/pool/, backend/threads/run/.

7. No file at backend/ root other than __init__.py.

8. protocols/ top-level has: agent_runtime.py, runtime_read.py,
   README.md, __init__.py.

9. No Python file at top level imports backend.* from core/, sandbox/,
   storage/, messaging/, protocols/, config/ (the reverse-dep rule).

The checker is deliberately conservative: it checks file/directory shape,
not import content (except rule 9). Missing files inside required dirs
are NOT checked — this script verifies the skeleton, not completeness.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"


FORBIDDEN_ROOT_FILE_PREFIXES = [
    "sandbox_",
    "auth_",
    "avatar_",
    "resource_",
    "user_sandbox_",
    "user_resource_",
    "supabase_runtime",
    "local_workspace",
]

FORBIDDEN_ROOT_FILES_EXACT = {
    "profile.py",
    "contact_bootstrap.py",
    "recipe_bootstrap.py",
    "virtual_threads.py",
    "message_content.py",
    "event_bus.py",
    "file_channel.py",
    "display_builder.py",
    "library_paths.py",
    "versioning.py",
    "agent_user_snapshot_apply.py",
    "app_entrypoint.py",
    "request_app.py",
    "runtime_storage_bootstrap.py",
    "storage_container_cache.py",
}

FORBIDDEN_BACKEND_DIRS = {
    "utils",
    "common",
    "shared",
    "helpers",
    "thread_runtime",
    "agent_runtime",
    "protocols",
}

REQUIRED_TOP_LEVEL_DIRS = [
    "protocols",
    "core",
    "sandbox",
    "storage",
    "messaging",
    "config",
]

REQUIRED_BACKEND_SUBDIRS = [
    "web",
    "chat",
    "identity",
    "threads",
    "sandboxes",
    "library",
    "hub",
    "monitor",
    "bootstrap",
]

REQUIRED_SUB_SUB_PACKAGES = [
    "backend/identity/auth",
    "backend/identity/avatar",
    "backend/sandboxes/runtime",
    "backend/sandboxes/resources",
    "backend/threads/chat_adapters",
    "backend/threads/display",
    "backend/threads/events",
    "backend/threads/pool",
    "backend/threads/run",
]

REQUIRED_PROTOCOLS_FILES = [
    "protocols/agent_runtime.py",
    "protocols/runtime_read.py",
    "protocols/__init__.py",
]

FORBIDDEN_WEB_SERVICES = "backend/web/services"

# For rule 9: top-level portable packages that must NOT import from backend/
TOP_LEVEL_PORTABLE = ["core", "sandbox", "storage", "messaging", "protocols", "config"]
BACKEND_IMPORT_RE = re.compile(r"^\s*(?:from\s+backend(?:\.|\s)|import\s+backend(?:\.|\s|$))", re.MULTILINE)


def check_forbidden_root_files() -> list[str]:
    violations: list[str] = []
    if not BACKEND.exists():
        return [f"backend/ directory not found at {BACKEND}"]
    for entry in sorted(BACKEND.iterdir()):
        if not entry.is_file() or entry.suffix != ".py":
            continue
        name = entry.name
        if name == "__init__.py":
            continue
        if name in FORBIDDEN_ROOT_FILES_EXACT:
            violations.append(f"forbidden root file: backend/{name} (must live in a subdomain)")
            continue
        for prefix in FORBIDDEN_ROOT_FILE_PREFIXES:
            if name.startswith(prefix):
                violations.append(f"forbidden root-prefix file: backend/{name} (must live in a subdomain)")
                break
        else:
            # File not in any forbidden list but also not __init__.py; anything else at backend/ root is suspicious.
            violations.append(f"unexpected root file: backend/{name} (only __init__.py is allowed at backend/ root)")
    return violations


def check_forbidden_backend_dirs() -> list[str]:
    violations: list[str] = []
    for name in FORBIDDEN_BACKEND_DIRS:
        path = BACKEND / name
        if path.exists():
            violations.append(f"forbidden directory: backend/{name}/ (see target layout; should not exist)")
    return violations


def check_forbidden_web_services() -> list[str]:
    if (REPO_ROOT / FORBIDDEN_WEB_SERVICES).exists():
        return [f"forbidden directory: {FORBIDDEN_WEB_SERVICES}/ (should have been drained in break #3)"]
    return []


def check_required_top_level_dirs() -> list[str]:
    violations: list[str] = []
    for name in REQUIRED_TOP_LEVEL_DIRS:
        path = REPO_ROOT / name
        if not path.is_dir():
            violations.append(f"missing required top-level dir: {name}/")
    return violations


def check_required_backend_subdirs() -> list[str]:
    violations: list[str] = []
    for name in REQUIRED_BACKEND_SUBDIRS:
        path = BACKEND / name
        if not path.is_dir():
            violations.append(f"missing required backend subdir: backend/{name}/")
            continue
        init_py = path / "__init__.py"
        if not init_py.is_file():
            violations.append(f"missing __init__.py in backend/{name}/")
    return violations


def check_required_sub_sub_packages() -> list[str]:
    violations: list[str] = []
    for rel in REQUIRED_SUB_SUB_PACKAGES:
        path = REPO_ROOT / rel
        if not path.is_dir():
            violations.append(f"missing required sub-sub-package: {rel}/")
            continue
        init_py = path / "__init__.py"
        if not init_py.is_file():
            violations.append(f"missing __init__.py in {rel}/")
    return violations


def check_required_protocols_files() -> list[str]:
    violations: list[str] = []
    for rel in REQUIRED_PROTOCOLS_FILES:
        path = REPO_ROOT / rel
        if not path.is_file():
            violations.append(f"missing required protocols file: {rel}")
    return violations


def check_no_reverse_import() -> list[str]:
    violations: list[str] = []
    for top in TOP_LEVEL_PORTABLE:
        top_path = REPO_ROOT / top
        if not top_path.is_dir():
            continue
        for py in top_path.rglob("*.py"):
            try:
                text = py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if BACKEND_IMPORT_RE.search(text):
                rel = py.relative_to(REPO_ROOT)
                violations.append(f"top-level file imports backend/: {rel}")
    return violations


CHECKS = [
    ("forbidden root files", check_forbidden_root_files),
    ("forbidden backend dirs", check_forbidden_backend_dirs),
    ("forbidden web/services", check_forbidden_web_services),
    ("required top-level dirs", check_required_top_level_dirs),
    ("required backend subdirs", check_required_backend_subdirs),
    ("required sub-sub-packages", check_required_sub_sub_packages),
    ("required protocols files", check_required_protocols_files),
    ("no top-level -> backend import", check_no_reverse_import),
]


def main() -> int:
    all_violations: list[tuple[str, str]] = []
    for name, fn in CHECKS:
        for v in fn():
            all_violations.append((name, v))

    if not all_violations:
        print("backend layout OK — all checks passed.")
        return 0

    print(f"backend layout check FAILED — {len(all_violations)} violation(s):")
    print()
    current = None
    for group, msg in all_violations:
        if group != current:
            print(f"  [{group}]")
            current = group
        print(f"    - {msg}")
    print()
    print("See program/doc/core/backend-package-dependencies-2026-04-20.md §3 for the target layout.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
