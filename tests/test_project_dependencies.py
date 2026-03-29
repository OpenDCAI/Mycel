import tomllib
from pathlib import Path


def test_httpx_dependency_includes_socks_support():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject_path.read_text())
    dependencies = project["project"]["dependencies"]

    assert "httpx>=0.28.1" in dependencies
    assert any(dep.startswith("socksio>=") for dep in dependencies)
