"""LSP Service - Language Server Protocol code intelligence via multilspy.

Registers a single DEFERRED `LSP` tool with 9 operations:
  goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol,
  goToImplementation, prepareCallHierarchy, incomingCalls, outgoingCalls

Sessions are managed by the process-level _LSPSessionPool singleton — they
start lazily on first use and persist for the lifetime of the process,
surviving agent restarts. Call `await lsp_pool.close_all()` on process exit.

Supported languages (via multilspy):
  python, typescript, javascript, go, rust, java, ruby, kotlin, csharp
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema

_FILE_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB — matches CC LSP limit

logger = logging.getLogger(__name__)

LSP_SCHEMA = make_tool_schema(
    name="LSP",
    description=(
        "Language Server Protocol code intelligence. "
        "Operations: goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol, "
        "goToImplementation, prepareCallHierarchy, incomingCalls, outgoingCalls. "
        "Language servers are auto-downloaded on first use. "
        "Supports python, typescript, javascript, go, rust, java, ruby, kotlin. "
        "file_path must be absolute. line/character are 1-based. "
        "incomingCalls/outgoingCalls require 'item' from prepareCallHierarchy output."
    ),
    properties={
        "operation": {
            "type": "string",
            "enum": [
                "goToDefinition",
                "findReferences",
                "hover",
                "documentSymbol",
                "workspaceSymbol",
                "goToImplementation",
                "prepareCallHierarchy",
                "incomingCalls",
                "outgoingCalls",
            ],
            "description": "LSP operation to perform",
        },
        "file_path": {
            "type": "string",
            "description": "Absolute path to file (required for all operations except workspaceSymbol)",
        },
        "line": {
            "type": "integer",
            "description": "1-based line number (required for goToDefinition, findReferences, hover)",
        },
        "character": {
            "type": "integer",
            "description": "1-based character offset (required for goToDefinition, findReferences, hover)",
        },
        "query": {
            "type": "string",
            "description": "Symbol name to search (required for workspaceSymbol)",
        },
        "language": {
            "type": "string",
            "description": "Language override. Auto-detected from file extension if omitted.",
        },
        "item": {
            "type": "object",
            "description": "CallHierarchyItem from prepareCallHierarchy (required for incomingCalls/outgoingCalls).",
        },
    },
    required=["operation"],
)

# File extension → multilspy language identifier
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".kt": "kotlin",
    ".cs": "csharp",
}


def _find_pyright() -> str | None:
    """Locate pyright-langserver: venv-local first, then PATH."""
    for name in ("pyright-langserver", "pyright_langserver"):
        # prefer the binary in the same venv as the current interpreter
        venv_bin = Path(os.__file__).parent.parent.parent / "bin" / name
        if venv_bin.exists():
            return str(venv_bin)
        found = shutil.which(name)
        if found:
            return found
    return None


class _PyrightSession:
    """Minimal asyncio LSP client for pyright-langserver (stdio).

    Used for Python operations not supported by Jedi:
    goToImplementation, prepareCallHierarchy, incomingCalls, outgoingCalls.

    Requires pyright in the active venv: pip install pyright
    """

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._reader_task: asyncio.Task | None = None
        self._open_files: set[str] = set()

    async def start(self) -> None:
        server = _find_pyright()
        if not server:
            raise RuntimeError("pyright-langserver not found. Install with: pip install pyright")
        self._proc = await asyncio.create_subprocess_exec(
            server,
            "--stdio",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(self._read_loop(), name="pyright-reader")

        # LSP handshake
        await self._request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": Path(self._workspace_root).as_uri(),
                "capabilities": {
                    "textDocument": {
                        "synchronization": {"dynamicRegistration": False},
                        "implementation": {"dynamicRegistration": False, "linkSupport": True},
                        "callHierarchy": {"dynamicRegistration": False},
                    }
                },
                "initializationOptions": {},
            },
        )
        self._notify("initialized", {})

    # ── I/O ───────────────────────────────────────────────────────────

    async def _read_loop(self) -> None:
        try:
            while True:
                assert self._proc and self._proc.stdout
                # Read headers until blank line
                content_length = 0
                while True:
                    raw = await self._proc.stdout.readline()
                    if not raw:
                        return
                    line = raw.decode().rstrip()
                    if not line:
                        break
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":", 1)[1].strip())
                if content_length == 0:
                    continue
                body = await self._proc.stdout.readexactly(content_length)
                msg = json.loads(body)
                # Route response/error to waiting Future
                msg_id = msg.get("id")
                msg_method = msg.get("method", "")
                if msg_id is not None and msg_method:
                    # Server-to-client request — must acknowledge with a response
                    self._write({"jsonrpc": "2.0", "id": msg_id, "result": None})
                    await self._drain()
                elif msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(RuntimeError(f"{msg['error'].get('message', 'LSP error')} ({msg['error'].get('code', '')})"))
                        else:
                            fut.set_result(msg.get("result"))
                # All other notifications ($/progress, diagnostics, etc.) are silently dropped
        except Exception as exc:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(exc)

    def _write(self, msg: dict) -> None:
        """Encode and buffer one LSP message (call drain() to flush)."""
        assert self._proc and self._proc.stdin
        body = json.dumps(msg, separators=(",", ":")).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        self._proc.stdin.write(header + body)

    async def _drain(self) -> None:
        assert self._proc and self._proc.stdin
        await self._proc.stdin.drain()

    def _notify(self, method: str, params: Any) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method: str, params: Any, timeout: float = 30.0) -> Any:
        req_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        await self._drain()
        return await asyncio.wait_for(fut, timeout=timeout)

    # ── file lifecycle ────────────────────────────────────────────────

    def _open_file(self, abs_path: str) -> None:
        uri = Path(abs_path).as_uri()
        if uri in self._open_files:
            return
        try:
            text = Path(abs_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        self._notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "python", "version": 1, "text": text}})
        self._open_files.add(uri)

    def _abs(self, rel_path: str) -> str:
        return str(Path(self._workspace_root) / rel_path)

    # ── LSP operations ────────────────────────────────────────────────

    async def request_implementation(self, rel_path: str, line: int, col: int) -> list:
        abs_path = self._abs(rel_path)
        self._open_file(abs_path)
        await self._drain()
        uri = Path(abs_path).as_uri()
        response = await self._request(
            "textDocument/implementation",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": col},
            },
        )
        return self._normalise_locations(response)

    async def request_prepare_call_hierarchy(self, rel_path: str, line: int, col: int) -> list:
        abs_path = self._abs(rel_path)
        self._open_file(abs_path)
        await self._drain()
        uri = Path(abs_path).as_uri()
        response = await self._request(
            "textDocument/prepareCallHierarchy",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": col},
            },
        )
        # File stays open — callHierarchy/incomingCalls and outgoingCalls may need it
        return response or []

    async def request_incoming_calls(self, item: dict) -> list:
        response = await self._request("callHierarchy/incomingCalls", {"item": item})
        return response or []

    async def request_outgoing_calls(self, item: dict) -> list:
        response = await self._request("callHierarchy/outgoingCalls", {"item": item})
        return response or []

    @staticmethod
    def _normalise_locations(response: Any) -> list:
        if not response:
            return []
        if isinstance(response, dict):
            response = [response]
        out = []
        for loc in response:
            uri = loc.get("uri") or loc.get("targetUri", "")
            rng = loc.get("range") or loc.get("targetSelectionRange") or loc.get("targetRange") or {}
            out.append({"uri": uri, "absolutePath": uri.replace("file://", ""), "range": rng})
        return out

    # ── shutdown ──────────────────────────────────────────────────────

    async def stop(self) -> None:
        if self._proc:
            try:
                await asyncio.wait_for(self._request("shutdown", {}), timeout=5)
                self._notify("exit", {})
            except Exception:
                logger.exception("Pyright LSP shutdown request failed for workspace %s", self._workspace_root)
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:
                self._proc.kill()
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass


class _LSPSession:
    """Holds a multilspy LanguageServer alive in a background asyncio task.

    Pattern: start_server() is an async context manager that must stay open
    for the lifetime of the session. We enter it inside a background Task and
    use an Event to signal readiness. Stopping sets a second Event that causes
    the background task to exit the context and shut down the server process.
    """

    def __init__(self, language: str, workspace_root: str) -> None:
        self.language = language
        self._workspace_root = workspace_root
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._lsp: Any = None
        self._error: Exception | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"lsp-{self.language}")
        try:
            await asyncio.wait_for(asyncio.shield(self._ready.wait()), timeout=60)
        except TimeoutError:
            raise TimeoutError(f"LSP server for '{self.language}' did not start within 60s")
        if self._error:
            raise self._error

    async def _run(self) -> None:
        try:
            from multilspy import LanguageServer  # core dep — always available
            from multilspy.multilspy_config import MultilspyConfig
            from multilspy.multilspy_logger import MultilspyLogger

            config = MultilspyConfig.from_dict({"code_language": self.language})
            lsp_logger = MultilspyLogger()
            self._lsp = LanguageServer.create(config, lsp_logger, self._workspace_root)
            async with self._lsp.start_server():
                self._ready.set()
                await self._stop.wait()
        except Exception as e:
            self._error = e
            self._ready.set()  # unblock any waiters
            logger.error("[LSPService] %s server error: %s", self.language, e)

    async def stop(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

    # ── request methods ───────────────────────────────────────────────

    async def request_definition(self, rel_path: str, line: int, col: int) -> list:
        try:
            return await self._lsp.request_definition(rel_path, line, col) or []
        except AssertionError:
            return []  # multilspy asserts on None response (no definition found)

    async def request_references(self, rel_path: str, line: int, col: int) -> list:
        try:
            return await self._lsp.request_references(rel_path, line, col) or []
        except AssertionError:
            return []

    async def request_hover(self, rel_path: str, line: int, col: int) -> Any:
        try:
            return await self._lsp.request_hover(rel_path, line, col)
        except AssertionError:
            return None

    async def request_document_symbols(self, rel_path: str) -> list:
        try:
            symbols, _ = await self._lsp.request_document_symbols(rel_path)
            return symbols or []
        except AssertionError:
            return []

    async def request_workspace_symbol(self, query: str) -> list:
        return await self._lsp.request_workspace_symbol(query) or []

    # ── advanced ops (direct server.send, for servers that support them) ──

    async def request_implementation(self, rel_path: str, line: int, col: int) -> list:
        abs_uri = Path(self._workspace_root, rel_path).as_uri()
        with self._lsp.open_file(rel_path):
            response = await self._lsp.server.send.implementation(
                {"textDocument": {"uri": abs_uri}, "position": {"line": line, "character": col}}
            )
        if not response:
            return []
        if isinstance(response, dict):
            response = [response]
        out = []
        for item in response:
            if "uri" in item and "range" in item:
                item.setdefault("absolutePath", item["uri"].replace("file://", ""))
                out.append(item)
            elif "targetUri" in item:
                out.append(
                    {
                        "uri": item["targetUri"],
                        "absolutePath": item["targetUri"].replace("file://", ""),
                        "range": item.get("targetSelectionRange", item.get("targetRange", {})),
                    }
                )
        return out

    async def request_prepare_call_hierarchy(self, rel_path: str, line: int, col: int) -> list:
        abs_uri = Path(self._workspace_root, rel_path).as_uri()
        with self._lsp.open_file(rel_path):
            response = await self._lsp.server.send.prepare_call_hierarchy(
                {"textDocument": {"uri": abs_uri}, "position": {"line": line, "character": col}}
            )
        return response or []

    async def request_incoming_calls(self, item: dict) -> list:
        response = await self._lsp.server.send.incoming_calls({"item": item})
        return response or []

    async def request_outgoing_calls(self, item: dict) -> list:
        response = await self._lsp.server.send.outgoing_calls({"item": item})
        return response or []


class _LSPSessionPool:
    """Process-level singleton managing LSP sessions across all agent instances.

    Sessions are keyed by (language, workspace_root) and survive agent restarts.
    Call close_all() once at process exit (e.g. from backend lifespan shutdown).
    """

    def __init__(self) -> None:
        # (language, workspace_root) → _LSPSession
        self._sessions: dict[tuple[str, str], _LSPSession] = {}
        # workspace_root → _PyrightSession
        self._pyright: dict[str, _PyrightSession] = {}
        # In-flight start tasks to prevent duplicate starts under concurrent requests
        self._starting: dict[tuple[str, str], asyncio.Task] = {}
        self._starting_pyright: dict[str, asyncio.Task] = {}

    async def get_session(self, language: str, workspace_root: str) -> _LSPSession:
        key = (language, workspace_root)
        if key in self._sessions:
            return self._sessions[key]
        if key not in self._starting:

            async def _start() -> _LSPSession:
                logger.info("[LSPPool] starting %s language server (workspace=%s)...", language, workspace_root)
                s = _LSPSession(language, workspace_root)
                await s.start()
                self._sessions[key] = s
                self._starting.pop(key, None)
                logger.info("[LSPPool] %s language server ready", language)
                return s

            self._starting[key] = asyncio.create_task(_start(), name=f"lsp-start-{language}")
        return await self._starting[key]

    async def get_pyright(self, workspace_root: str) -> _PyrightSession:
        if workspace_root in self._pyright:
            return self._pyright[workspace_root]
        if workspace_root not in self._starting_pyright:

            async def _start() -> _PyrightSession:
                logger.info("[LSPPool] starting pyright (workspace=%s)...", workspace_root)
                s = _PyrightSession(workspace_root)
                await s.start()
                self._pyright[workspace_root] = s
                self._starting_pyright.pop(workspace_root, None)
                logger.info("[LSPPool] pyright ready")
                return s

            self._starting_pyright[workspace_root] = asyncio.create_task(_start(), name="lsp-start-pyright")
        return await self._starting_pyright[workspace_root]

    async def close_all(self) -> None:
        """Stop all running language server processes. Call once at process exit."""
        for (lang, ws), session in list(self._sessions.items()):
            try:
                await session.stop()
                logger.debug("[LSPPool] stopped %s server (workspace=%s)", lang, ws)
            except Exception as e:
                logger.debug("[LSPPool] error stopping %s: %s", lang, e)
        self._sessions.clear()
        for ws, session in list(self._pyright.items()):
            try:
                await session.stop()
                logger.debug("[LSPPool] stopped pyright (workspace=%s)", ws)
            except Exception as e:
                logger.debug("[LSPPool] error stopping pyright: %s", e)
        self._pyright.clear()


# Process-level singleton — import and use directly
lsp_pool = _LSPSessionPool()


class LSPService:
    """Registers the LSP tool (DEFERRED) into ToolRegistry.

    Delegates all session management to the process-level lsp_pool singleton.
    Language servers start lazily on first use and persist across agent restarts.
    """

    # Operations that Jedi doesn't support — routed to pyright for Python,
    # or to the native server.send.* for other languages.
    _ADVANCED_OPS: frozenset[str] = frozenset({"goToImplementation", "prepareCallHierarchy", "incomingCalls", "outgoingCalls"})

    def __init__(self, registry: ToolRegistry, workspace_root: str | Path) -> None:
        self._workspace_root = str(Path(workspace_root).resolve())
        registry.register(
            ToolEntry(
                name="LSP",
                mode=ToolMode.DEFERRED,
                schema=LSP_SCHEMA,
                handler=self._handle,
                source="LSPService",
                search_hint="language server definition references hover symbols go-to",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )
        logger.debug("[LSPService] registered (workspace=%s)", self._workspace_root)

    # ── session management (delegates to process-level pool) ──────────

    async def _get_session(self, language: str) -> _LSPSession:
        return await lsp_pool.get_session(language, self._workspace_root)

    async def _get_pyright(self) -> _PyrightSession:
        return await lsp_pool.get_pyright(self._workspace_root)

    def _detect_language(self, file_path: str) -> str | None:
        return _EXT_TO_LANG.get(Path(file_path).suffix.lower())

    def _to_relative(self, file_path: str) -> str:
        try:
            return str(Path(file_path).relative_to(self._workspace_root))
        except ValueError:
            return file_path

    # ── pre-flight checks ─────────────────────────────────────────────

    @staticmethod
    def _check_file(file_path: str) -> str | None:
        """Return error string if file exceeds 10 MB limit, else None."""
        try:
            size = Path(file_path).stat().st_size
        except OSError:
            return None  # let LSP handle missing file errors
        if size > _FILE_SIZE_LIMIT:
            mb = size / (1024 * 1024)
            return f"File too large ({mb:.1f} MB). LSP file size limit is 10 MB."
        return None

    def _filter_gitignored(self, locations: list) -> list:
        """Filter out locations inside gitignored paths (batches of 50, like CC)."""
        if not locations:
            return locations
        abs_paths = [loc.get("absolutePath") or loc.get("uri", "").replace("file://", "") for loc in locations]
        try:
            # git check-ignore exits 0 if any path is ignored, 1 if none are
            result = subprocess.run(
                ["git", "check-ignore", "--stdin", "-z"],
                input="\0".join(abs_paths),
                capture_output=True,
                text=True,
                cwd=self._workspace_root,
                timeout=5,
            )
            ignored = set(result.stdout.split("\0")) if result.stdout else set()
        except Exception:
            return locations  # on error, return all (fail-open)
        return [loc for loc, p in zip(locations, abs_paths) if p not in ignored]

    def _filter_gitignored_batched(self, locations: list) -> list:
        """Run _filter_gitignored in batches of 50 (matches CC batch size)."""
        out = []
        for i in range(0, len(locations), 50):
            out.extend(self._filter_gitignored(locations[i : i + 50]))
        return out

    async def _filter_gitignored_batched_async(self, locations: list) -> list:
        return await asyncio.to_thread(self._filter_gitignored_batched, locations)

    # ── output formatters ─────────────────────────────────────────────

    @staticmethod
    def _fmt_location(loc: Any) -> dict:
        start = loc.get("range", {}).get("start", {})
        return {
            "file": loc.get("absolutePath") or loc.get("uri", ""),
            "line": start.get("line", 0),
            "column": start.get("character", 0),
        }

    @staticmethod
    def _fmt_hover(result: Any) -> str:
        contents = result.get("contents", "")
        if isinstance(contents, dict):
            return contents.get("value", str(contents))
        if isinstance(contents, list):
            parts = []
            for c in contents:
                parts.append(c.get("value", str(c)) if isinstance(c, dict) else str(c))
            return "\n".join(parts)
        return str(contents)

    @staticmethod
    def _fmt_symbol(sym: Any) -> dict:
        loc = sym.get("location") or {}
        if loc:
            # SymbolInformation (workspaceSymbol) — location.uri + location.range
            start = loc.get("range", {}).get("start", {})
            uri = loc.get("uri", "")
            file = loc.get("absolutePath") or (uri.replace("file://", "") if uri.startswith("file://") else uri)
        else:
            # DocumentSymbol (documentSymbol) — range/selectionRange at top level, no file
            start = sym.get("selectionRange", sym.get("range", {})).get("start", {})
            file = ""
        return {
            "name": sym.get("name", ""),
            "kind": sym.get("kind"),
            "file": file,
            "line": start.get("line"),
        }

    @staticmethod
    def _fmt_call_hierarchy_item(item: Any) -> dict:
        uri = item.get("uri", "")
        start = item.get("range", {}).get("start", {})
        return {
            "name": item.get("name", ""),
            "kind": item.get("kind"),
            "file": uri.replace("file://", "") if uri.startswith("file://") else uri,
            "line": start.get("line"),
            "item": item,  # pass-through for incomingCalls/outgoingCalls
        }

    @staticmethod
    def _fmt_call_hierarchy_call(call: Any, direction: str) -> dict:
        item_key = "from" if direction == "incoming" else "to"
        caller = call.get(item_key, {})
        uri = caller.get("uri", "")
        start = caller.get("range", {}).get("start", {})
        ranges = [r.get("start", {}) for r in call.get(f"{item_key}Ranges", [])]
        return {
            "name": caller.get("name", ""),
            "kind": caller.get("kind"),
            "file": uri.replace("file://", "") if uri.startswith("file://") else uri,
            "line": start.get("line"),
            "call_sites": [{"line": r.get("line"), "column": r.get("character")} for r in ranges],
            "item": caller,  # pass-through for chaining
        }

    # ── tool handler ──────────────────────────────────────────────────

    async def _handle(
        self,
        operation: str,
        file_path: str | None = None,
        line: int | None = None,
        character: int | None = None,
        query: str | None = None,
        language: str | None = None,
        item: dict | None = None,
    ) -> str:
        # Resolve language (incomingCalls/outgoingCalls carry language in item["uri"])
        lang = language
        if not lang and file_path:
            lang = self._detect_language(file_path)
        if not lang and operation in ("incomingCalls", "outgoingCalls") and item:
            uri = item.get("uri", "")
            lang = self._detect_language(uri)
        if not lang:
            supported = ", ".join(sorted(set(_EXT_TO_LANG.values())))
            return f"Cannot detect language. Set 'language' parameter. Supported: {supported}"

        # 10 MB file size guard (matches CC LSP limit)
        if file_path:
            err = self._check_file(file_path)
            if err:
                return err

        # Python advanced ops → pyright; other languages → multilspy server.send.*
        use_pyright = lang == "python" and operation in self._ADVANCED_OPS

        pyright: _PyrightSession | None = None
        session: _LSPSession | None = None

        if use_pyright:
            try:
                pyright = await self._get_pyright()
            except Exception as e:
                return f"Failed to start pyright language server: {e}"
        else:
            try:
                session = await self._get_session(lang)
            except Exception as e:
                return f"Failed to start {lang} language server: {e}"

        rel = self._to_relative(file_path) if file_path else ""
        # @@@dt-04-lsp-position-contract - CC exposes editor-facing 1-based
        # positions and converts at the tool boundary. Leon must do the same
        # or every position-aware operation silently lands one symbol off.
        zero_line = line - 1 if line is not None else None
        zero_character = character - 1 if character is not None else None

        try:
            if operation == "goToDefinition":
                if not file_path or zero_line is None or zero_character is None:
                    return "goToDefinition requires: file_path, line, character"
                assert session is not None
                results = await session.request_definition(rel, zero_line, zero_character)
                results = await self._filter_gitignored_batched_async(results)
                if not results:
                    return "No definition found."
                return json.dumps([self._fmt_location(r) for r in results], indent=2)

            elif operation == "findReferences":
                if not file_path or zero_line is None or zero_character is None:
                    return "findReferences requires: file_path, line, character"
                assert session is not None
                results = await session.request_references(rel, zero_line, zero_character)
                results = await self._filter_gitignored_batched_async(results)
                if not results:
                    return "No references found."
                return json.dumps([self._fmt_location(r) for r in results], indent=2)

            elif operation == "hover":
                if not file_path or zero_line is None or zero_character is None:
                    return "hover requires: file_path, line, character"
                assert session is not None
                result = await session.request_hover(rel, zero_line, zero_character)
                if not result:
                    return "No hover info."
                return self._fmt_hover(result)

            elif operation == "documentSymbol":
                if not file_path:
                    return "documentSymbol requires: file_path"
                assert session is not None
                symbols = await session.request_document_symbols(rel)
                if not symbols:
                    return "No symbols found."
                return json.dumps([self._fmt_symbol(s) for s in symbols], indent=2)

            elif operation == "workspaceSymbol":
                if not query:
                    return "workspaceSymbol requires: query"
                assert session is not None
                symbols = await session.request_workspace_symbol(query)
                if not symbols:
                    return f"No symbols matching '{query}'."
                return json.dumps([self._fmt_symbol(s) for s in symbols], indent=2)

            elif operation == "goToImplementation":
                if not file_path or zero_line is None or zero_character is None:
                    return "goToImplementation requires: file_path, line, character"
                src = pyright if use_pyright else session
                assert src is not None
                results = await src.request_implementation(rel, zero_line, zero_character)
                results = await self._filter_gitignored_batched_async(results)
                if not results:
                    return "No implementation found."
                return json.dumps([self._fmt_location(r) for r in results], indent=2)

            elif operation == "prepareCallHierarchy":
                if not file_path or zero_line is None or zero_character is None:
                    return "prepareCallHierarchy requires: file_path, line, character"
                src = pyright if use_pyright else session
                assert src is not None
                items = await src.request_prepare_call_hierarchy(rel, zero_line, zero_character)
                if not items:
                    return "No call hierarchy items found."
                return json.dumps([self._fmt_call_hierarchy_item(i) for i in items], indent=2)

            elif operation == "incomingCalls":
                if not item:
                    return "incomingCalls requires: item (CallHierarchyItem from prepareCallHierarchy)"
                src = pyright if use_pyright else session
                assert src is not None
                calls = await src.request_incoming_calls(item)
                if not calls:
                    return "No incoming calls found."
                return json.dumps([self._fmt_call_hierarchy_call(c, "incoming") for c in calls], indent=2)

            elif operation == "outgoingCalls":
                if not item:
                    return "outgoingCalls requires: item (CallHierarchyItem from prepareCallHierarchy)"
                src = pyright if use_pyright else session
                assert src is not None
                calls = await src.request_outgoing_calls(item)
                if not calls:
                    return "No outgoing calls found."
                return json.dumps([self._fmt_call_hierarchy_call(c, "outgoing") for c in calls], indent=2)

            else:
                return (
                    f"Unknown operation '{operation}'. "
                    "Valid: goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol, "
                    "goToImplementation, prepareCallHierarchy, incomingCalls, outgoingCalls"
                )

        except Exception as e:
            logger.exception("[LSPService] operation=%s failed", operation)
            return f"LSP error: {e}"
