from pathlib import Path


def test_broad_monitor_shell_is_retired():
    repo_root = Path(__file__).resolve().parents[3]
    retired_module = "monitor" + "_service"

    assert not (repo_root / f"backend/web/services/{retired_module}.py").exists()

    remaining_imports = []
    for root in ("backend", "tests"):
        for path in (repo_root / root).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if retired_module in source:
                remaining_imports.append(path.relative_to(repo_root).as_posix())

    assert remaining_imports == []
