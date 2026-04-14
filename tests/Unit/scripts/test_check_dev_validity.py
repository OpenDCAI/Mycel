from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "check-dev-validity.sh"


REQUIRED_ENV = {
    "LEON_STORAGE_STRATEGY": "supabase",
    "LEON_SUPABASE_CLIENT_FACTORY": "backend.web.core.supabase_factory:create_supabase_client",
    "LEON_DB_SCHEMA": "staging",
    "SUPABASE_PUBLIC_URL": "https://supabase.mycel.nextmind.space",
    "SUPABASE_INTERNAL_URL": "https://supabase.mycel.nextmind.space",
    "SUPABASE_AUTH_URL": "https://supabase.mycel.nextmind.space/auth/v1",
    "SUPABASE_ANON_KEY": "anon",
    "LEON_SUPABASE_SERVICE_ROLE_KEY": "service-role",
    "SUPABASE_JWT_SECRET": "jwt-secret",
    "LEON_POSTGRES_URL": "postgresql://postgres:pw@127.0.0.1:5432/postgres",
    "OPENAI_API_KEY": "sk-test",
    "MYCEL_BACKEND_BASE_URL": "http://127.0.0.1:1",
    "MYCEL_SMOKE_IDENTIFIER": "coder@example.com",
    "MYCEL_SMOKE_PASSWORD": "pw-123456",
}


class _SmokeHandler(BaseHTTPRequestHandler):
    agents_payload = {"items": [{"id": "agent-1", "name": "Toad"}]}
    default_config_payload = {
        "source": "derived",
        "config": {
            "create_mode": "new",
            "provider_config": "local",
            "sandbox_template_id": None,
            "sandbox_template": None,
        },
    }

    def _write_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/auth/login":
            self._write_json(404, {"detail": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if payload != {"identifier": "coder@example.com", "password": "pw-123456"}:
            self._write_json(401, {"detail": "bad credentials"})
            return
        self._write_json(200, {"token": "tok-1"})

    def do_GET(self) -> None:  # noqa: N802
        auth_header = self.headers.get("Authorization")
        if auth_header != "Bearer tok-1":
            self._write_json(401, {"detail": "missing bearer"})
            return
        if self.path == "/api/panel/agents":
            self._write_json(200, type(self).agents_payload)
            return
        if self.path == "/api/threads/default-config?agent_user_id=agent-1":
            self._write_json(200, type(self).default_config_payload)
            return
        self._write_json(404, {"detail": "not found"})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class CheckDevValidityScriptTests(unittest.TestCase):
    def _run_script(self, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "")}
        env.update(extra_env)
        command = [str(SCRIPT)]
        if os.name == "nt":
            command = [shutil.which("bash") or "bash", str(SCRIPT)]
        return subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_fails_loudly_when_required_env_is_missing(self) -> None:
        result = self._run_script({})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required environment variables", result.stderr)
        self.assertIn("LEON_STORAGE_STRATEGY", result.stderr)
        self.assertIn("MYCEL_BACKEND_BASE_URL", result.stderr)

    def test_fails_when_owner_has_no_agents_for_default_config_probe(self) -> None:
        class EmptyAgentHandler(_SmokeHandler):
            agents_payload = {"items": []}

        with ThreadingHTTPServer(("127.0.0.1", 0), EmptyAgentHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = self._run_script(
                    {
                        **REQUIRED_ENV,
                        "MYCEL_BACKEND_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    }
                )
            finally:
                server.shutdown()
                thread.join()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/api/panel/agents returned no owned agents", result.stderr)

    def test_fails_when_default_config_payload_is_frontend_malformed(self) -> None:
        class MalformedDefaultConfigHandler(_SmokeHandler):
            default_config_payload = {
                "config": {
                    "provider_config": "local",
                },
            }

        with ThreadingHTTPServer(("127.0.0.1", 0), MalformedDefaultConfigHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = self._run_script(
                    {
                        **REQUIRED_ENV,
                        "MYCEL_BACKEND_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    }
                )
            finally:
                server.shutdown()
                thread.join()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/api/threads/default-config returned malformed launch config", result.stderr)

    def test_passes_when_real_smoke_sequence_succeeds(self) -> None:
        with ThreadingHTTPServer(("127.0.0.1", 0), _SmokeHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = self._run_script(
                    {
                        **REQUIRED_ENV,
                        "MYCEL_BACKEND_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    }
                )
            finally:
                server.shutdown()
                thread.join()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("dev validity smoke passed", result.stdout)
        self.assertIn("login ok", result.stdout)
        self.assertIn("default-config ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
