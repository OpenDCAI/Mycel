"""Console-script entrypoint for the Stage-1 agent CLI."""

from __future__ import annotations

import sys

from .commands import run_cli


def main() -> int:
    return run_cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
