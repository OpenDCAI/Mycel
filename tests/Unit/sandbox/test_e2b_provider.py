"""Smoke test for E2B provider and sandbox."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox.providers.e2b import E2BProvider


def test_e2b_provider():
    api_key = os.getenv("E2B_API_KEY")
    if not api_key:
        print("E2B_API_KEY not set, skipping")
        return

    provider = E2BProvider(api_key=api_key, timeout=60)

    # Create
    print("Creating session...")
    info = provider.create_session()
    print(f"  session_id: {info.session_id}")
    sid = info.session_id

    # Execute
    print("\nExecuting command...")
    result = provider.execute(sid, "echo hello && uname -a")
    print(f"  output: {result.output}")
    assert result.exit_code == 0

    # Write file
    print("\nWriting file...")
    provider.write_file(sid, "/home/user/test.txt", "hello from leon")

    # Read file
    print("\nReading file...")
    content = provider.read_file(sid, "/home/user/test.txt")
    print(f"  content: {content}")
    assert content == "hello from leon"

    # List dir
    print("\nListing /home/user...")
    items = provider.list_dir(sid, "/home/user")
    names = [i["name"] for i in items]
    print(f"  entries: {names}")
    assert "test.txt" in names

    # Status
    print("\nChecking status...")
    status = provider.get_session_status(sid)
    print(f"  status: {status}")
    assert status == "running"

    # Pause
    print("\nPausing...")
    assert provider.pause_session(sid)

    # Status after pause
    status = provider.get_session_status(sid)
    print(f"  status after pause: {status}")
    assert status == "paused"

    # Resume
    print("\nResuming...")
    assert provider.resume_session(sid)

    # Verify state survived
    content = provider.read_file(sid, "/home/user/test.txt")
    print(f"  content after resume: {content}")
    assert content == "hello from leon"

    # Destroy
    print("\nDestroying...")
    assert provider.destroy_session(sid)

    print("\nAll tests passed!")


if __name__ == "__main__":
    test_e2b_provider()
