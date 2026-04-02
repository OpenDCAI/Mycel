"""LSP Service - Language Server Protocol code intelligence via multilspy.

Registers a single DEFERRED `LSP` tool with 9 operations:
  goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol,
  goToImplementation, prepareCallHierarchy, incomingCalls, outgoingCalls

Language servers are auto-downloaded on first use per language. The server
process is started lazily on the first LSP call and kept alive until close().

Supported languages (via multilspy):
  python, typescript, javascript, go, rust, java, ruby, kotlin, csharp
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

_FILE_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB — matches CC LSP limit

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

logger = logging.getLogger(__name__)

LSP_SCHEMA = {
    "name": "LSP",
    "description": (
        "Language Server Protocol code intelligence. "
        "Operations: goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol, "
        "goToImplementation, prepareCallHierarchy, incomingCalls, outgoingCalls. "
        "Language servers are auto-downloaded on first use. "
        "Supports python, typescript, javascript, go, rust, java, ruby, kotlin. "
        "file_path must be absolute. line/column are zero-based. "
        "incomingCalls/outgoingCalls require 'item' from prepareCallHierarchy output."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "goToDefinition", "findReferences", "hover", "documentSymbol", "workspaceSymbol",
                    "goToImplementation", "prepareCallHierarchy", "incomingCalls", "outgoingCalls",
                ],
                "description": "LSP operation to perform",
            },
            "file_path": {
                "type": "string",
                "description": "Absolute path to file (required for all operations except workspaceSymbol)",
            },
            "line": {
                "type": "integer",
                "description": "Zero-based line number (required for goToDefinition, findReferences, hover)",
            },
            "column": {
                "type": "integer",
                "description": "Zero-based column number (required for goToDefinition, findReferences, hover)",
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
        "required": ["operation"],
    },
}

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
        except asyncio.TimeoutError:
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
            except (asyncio.TimeoutError, asyncio.CancelledError):
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

    async def request_implementation(self, rel_path: str, line: int, col: int) -> list:
        import pathlib as _pathlib
        abs_uri = _pathlib.Path(self._workspace_root, rel_path).as_uri()
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
                out.append({
                    "uri": item["targetUri"],
                    "absolutePath": item["targetUri"].replace("file://", ""),
                    "range": item.get("targetSelectionRange", item.get("targetRange", {})),
                })
        return out

    async def request_prepare_call_hierarchy(self, rel_path: str, line: int, col: int) -> list:
        import pathlib as _pathlib
        abs_uri = _pathlib.Path(self._workspace_root, rel_path).as_uri()
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


class LSPService:
    """Registers the LSP tool (DEFERRED) into ToolRegistry.

    The language server is started lazily on the first request per language
    and kept alive until close() is called (typically at agent shutdown).
    """

    def __init__(self, registry: ToolRegistry, workspace_root: str | Path) -> None:
        self._workspace_root = str(Path(workspace_root).resolve())
        self._sessions: dict[str, _LSPSession] = {}
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
        logger.info("LSPService initialized (workspace=%s)", self._workspace_root)

    # ── session management ────────────────────────────────────────────

    async def _get_session(self, language: str) -> _LSPSession:
        if language not in self._sessions:
            logger.info("[LSPService] starting %s language server...", language)
            session = _LSPSession(language, self._workspace_root)
            await session.start()
            self._sessions[language] = session
            logger.info("[LSPService] %s language server ready", language)
        return self._sessions[language]

    def _detect_language(self, file_path: str) -> str | None:
        return _EXT_TO_LANG.get(Path(file_path).suffix.lower())

    def _to_relative(self, file_path: str) -> str:
        try:
            return str(Path(file_path).relative_to(self._workspace_root))
        except ValueError:
            return file_path  # fallback: pass as-is

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
            out.extend(self._filter_gitignored(locations[i:i + 50]))
        return out

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
        column: int | None = None,
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

        try:
            session = await self._get_session(lang)
        except Exception as e:
            return f"Failed to start {lang} language server: {e}"

        rel = self._to_relative(file_path) if file_path else ""

        try:
            if operation == "goToDefinition":
                if not file_path or line is None or column is None:
                    return "goToDefinition requires: file_path, line, column"
                results = await session.request_definition(rel, line, column)
                results = self._filter_gitignored_batched(results)
                if not results:
                    return "No definition found."
                return json.dumps([self._fmt_location(r) for r in results], indent=2)

            elif operation == "findReferences":
                if not file_path or line is None or column is None:
                    return "findReferences requires: file_path, line, column"
                results = await session.request_references(rel, line, column)
                results = self._filter_gitignored_batched(results)
                if not results:
                    return "No references found."
                return json.dumps([self._fmt_location(r) for r in results], indent=2)

            elif operation == "hover":
                if not file_path or line is None or column is None:
                    return "hover requires: file_path, line, column"
                result = await session.request_hover(rel, line, column)
                if not result:
                    return "No hover info."
                return self._fmt_hover(result)

            elif operation == "documentSymbol":
                if not file_path:
                    return "documentSymbol requires: file_path"
                symbols = await session.request_document_symbols(rel)
                if not symbols:
                    return "No symbols found."
                return json.dumps([self._fmt_symbol(s) for s in symbols], indent=2)

            elif operation == "workspaceSymbol":
                if not query:
                    return "workspaceSymbol requires: query"
                symbols = await session.request_workspace_symbol(query)
                if not symbols:
                    return f"No symbols matching '{query}'."
                return json.dumps([self._fmt_symbol(s) for s in symbols], indent=2)

            elif operation == "goToImplementation":
                if not file_path or line is None or column is None:
                    return "goToImplementation requires: file_path, line, column"
                results = await session.request_implementation(rel, line, column)
                results = self._filter_gitignored_batched(results)
                if not results:
                    return "No implementation found."
                return json.dumps([self._fmt_location(r) for r in results], indent=2)

            elif operation == "prepareCallHierarchy":
                if not file_path or line is None or column is None:
                    return "prepareCallHierarchy requires: file_path, line, column"
                items = await session.request_prepare_call_hierarchy(rel, line, column)
                if not items:
                    return "No call hierarchy items found."
                return json.dumps([self._fmt_call_hierarchy_item(i) for i in items], indent=2)

            elif operation == "incomingCalls":
                if not item:
                    return "incomingCalls requires: item (CallHierarchyItem from prepareCallHierarchy)"
                calls = await session.request_incoming_calls(item)
                if not calls:
                    return "No incoming calls found."
                return json.dumps([self._fmt_call_hierarchy_call(c, "incoming") for c in calls], indent=2)

            elif operation == "outgoingCalls":
                if not item:
                    return "outgoingCalls requires: item (CallHierarchyItem from prepareCallHierarchy)"
                calls = await session.request_outgoing_calls(item)
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

    async def close(self) -> None:
        """Stop all running language server sessions."""
        for lang, session in list(self._sessions.items()):
            try:
                await session.stop()
                logger.debug("[LSPService] stopped %s server", lang)
            except Exception as e:
                logger.debug("[LSPService] error stopping %s: %s", lang, e)
        self._sessions.clear()
