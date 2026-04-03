#!/usr/bin/env python3
"""Register then login against a running backend.

This is a developer convenience helper only.
It does not participate in runtime auth decisions.
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    with httpx.Client(timeout=20.0) as client:
        register = client.post(
            f"{args.base_url}/api/auth/register",
            json={"username": args.username, "password": args.password},
        )
        print("REGISTER", register.status_code)
        if register.status_code not in (200, 409):
            print(register.text)
            return 1

        login = client.post(
            f"{args.base_url}/api/auth/login",
            json={"username": args.username, "password": args.password},
        )
        print("LOGIN", login.status_code)
        if login.status_code != 200:
            print(login.text)
            return 1

        payload = login.json()
        print(
            json.dumps(
                {
                    "token": payload.get("token"),
                    "user": payload.get("user"),
                    "agent": payload.get("agent"),
                    "entity_id": payload.get("entity_id"),
                },
                ensure_ascii=True,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
