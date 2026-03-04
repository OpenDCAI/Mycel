from pathlib import Path

from sandbox.local import LocalSessionProvider


def test_local_session_provider_execute_and_filesystem(tmp_path: Path):
    provider = LocalSessionProvider(default_cwd=str(tmp_path))
    session = provider.create_session()
    sid = session.session_id

    result = provider.execute(sid, "echo hello-local")
    assert result.exit_code == 0
    assert "hello-local" in result.output

    target = tmp_path / "nested" / "note.txt"
    provider.write_file(sid, str(target), "content-ok")
    assert provider.read_file(sid, str(target)) == "content-ok"

    listing = provider.list_dir(sid, str(target.parent))
    assert any(item["name"] == "note.txt" and item["type"] == "file" for item in listing)
