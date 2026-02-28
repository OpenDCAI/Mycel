"""Run a small SWE-bench slice with LeonAgent and evaluate via official harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datasets import load_dataset
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from swebench.harness.constants import KEY_INSTANCE_ID, KEY_MODEL, KEY_PREDICTION

from agent import LeonAgent
from config.models_loader import ModelsLoader
from sandbox.thread_context import set_current_thread_id

INVALID_TOOL_MESSAGE_RE = re.compile(r"error:\s*([^\s]+)\s+is not a valid tool", re.IGNORECASE)


def run(cmd: list[str], cwd: Path | None = None, timeout_sec: int | None = None) -> str:
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"command timeout after {timeout_sec}s\ncmd={' '.join(cmd)}"
        ) from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed rc={proc.returncode}\ncmd={' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


def run_capture(
    cmd: list[str],
    cwd: Path | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            env=env,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": -1,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
            "timeout_sec": timeout_sec,
        }


def _has_commit(repo_dir: Path, commit: str) -> bool:
    env = dict(os.environ)
    env.setdefault("GIT_NO_LAZY_FETCH", "1")
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "cat-file", "-e", f"{commit}^{{commit}}"],
        text=True,
        capture_output=True,
        env=env,
    )
    return proc.returncode == 0


def _cleanup_stale_git_lock(repo_dir: Path, lock_name: str) -> bool:
    lock_path = repo_dir / ".git" / lock_name
    if not lock_path.exists():
        return False
    lock_path.unlink()
    print(f"[slice] git_lock_cleanup repo={repo_dir} lock={lock_path}")
    return True


def _fetch_target_commit(repo_dir: Path, base_commit: str, git_timeout_sec: int) -> None:
    fetch_cmd = ["git", "-C", str(repo_dir), "fetch", "--no-tags", "origin", base_commit, "--depth=1"]
    try:
        run(fetch_cmd, timeout_sec=git_timeout_sec)
        return
    except Exception as exc:
        err = str(exc)
        if "shallow.lock" not in err:
            raise
        cleaned = _cleanup_stale_git_lock(repo_dir, "shallow.lock")
        if not cleaned:
            raise
        print(f"[slice] git_fetch_retry repo={repo_dir} commit={base_commit}")
        run(fetch_cmd, timeout_sec=git_timeout_sec)


def ensure_repo_cache(repo: str, base_commit: str, cache_root: Path, git_timeout_sec: int) -> Path:
    repo_dir = cache_root / repo.replace("/", "__")
    if not repo_dir.exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        # @@@repo-cache-partial-clone - use blobless clone for faster first-time cache warmup on large repos.
        run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", f"https://github.com/{repo}.git", str(repo_dir)],
            timeout_sec=git_timeout_sec,
        )
    if not _has_commit(repo_dir, base_commit):
        # @@@fetch-target-commit-only - fetch only missing target commit to avoid expensive full remote fetch on every instance.
        _fetch_target_commit(repo_dir=repo_dir, base_commit=base_commit, git_timeout_sec=git_timeout_sec)
    return repo_dir


def classify_instance_error(message: str) -> str:
    lowered = message.lower()
    if "authenticationerror" in lowered or "令牌验证失败" in lowered or "one_api_error" in lowered:
        return "auth"
    if "shallow.lock" in lowered:
        return "repo_lock"
    if "graphrecursionerror" in lowered:
        return "recursion_limit"
    if "command timeout after" in lowered or "timeouterror" in lowered:
        return "timeout"
    return "runtime"


def parse_tests(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    raise ValueError(f"unsupported tests payload: {type(raw)}")


def build_prompt(row: dict[str, Any], prompt_profile: str) -> str:
    fail_tests = parse_tests(row.get("FAIL_TO_PASS"))
    pass_tests = parse_tests(row.get("PASS_TO_PASS"))
    pass_preview = pass_tests[:20]
    prompt = [
        "You are solving one SWE-bench task in the current repository.",
        "",
        "Rules:",
        "1. Make the minimal code change required by the issue.",
        "2. Run focused tests before finishing.",
        "3. Do not touch unrelated files.",
        "4. Use tool name `run_command` for shell execution; do not call a tool named `bash`.",
        "5. Use `python3` instead of `python` in commands.",
        "",
        f"Instance: {row['instance_id']}",
        f"Repo: {row['repo']}",
        "",
        "Issue statement:",
        str(row["problem_statement"]).strip(),
        "",
        "Hints:",
        str(row.get("hints_text", "")).strip() or "(none)",
        "",
        "Tests that should pass after your fix:",
        *[f"- {t}" for t in fail_tests],
    ]
    if pass_preview:
        prompt.extend(["", "Regression tests to keep passing (preview):", *[f"- {t}" for t in pass_preview]])
    if prompt_profile == "heuristic":
        prompt.extend(
            [
                "",
                "Execution constraints (strict):",
                "- Keep a tight budget: at most 12 tool calls total for this task.",
                "- Stop early once you have enough evidence for a minimal fix; do not continue exploring.",
                "- If the same command pattern fails twice without new information, stop tool use.",
                "- If key tests pass OR you cannot make further progress with high confidence, stop tool use immediately.",
                "- Final turn must be plain text only: provide (1) files changed, (2) why the fix works, (3) tests run + results, (4) remaining risks.",
                "- Before finishing, you MUST explicitly run each test listed in 'Tests that should pass after your fix' above using run_command, and show the output. Passing your own ad-hoc tests is NOT sufficient.",
                "- After the final summary, do not call any tools.",
            ]
        )
    prompt.extend(
        [
            "",
            "At the end, summarize what you changed and why.",
        ]
    )
    return "\n".join(prompt)


def build_thread_id(thread_prefix: str, run_stamp: str, instance_id: str) -> str:
    safe_stamp = re.sub(r"[^a-zA-Z0-9_.-]+", "-", run_stamp)
    return f"{thread_prefix}-{safe_stamp}-{instance_id}"


def run_fail_to_pass_gate(row: dict[str, Any], workspace: Path) -> dict[str, Any]:
    try:
        fail_tests = parse_tests(row.get("FAIL_TO_PASS"))
    except Exception as error:
        print(f"[slice] fail_to_pass_parse_error instance={row.get('instance_id')} error={error}")
        return {
            "status": "parse_error",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "results": [
                {
                    "error": str(error),
                    "raw_fail_to_pass": str(row.get("FAIL_TO_PASS", ""))[:300],
                }
            ],
        }
    if not fail_tests:
        return {
            "status": "no_fail_to_pass_tests",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "results": [],
        }

    timeout_sec = int(os.getenv("FAIL_TO_PASS_TEST_TIMEOUT_SEC", "300"))
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    # @@@fail-to-pass-runtime-gate - enforce SWE-bench success criteria with real post-patch test execution.
    for test_name in fail_tests:
        cmd = ["python3", "-m", "pytest", test_name]
        captured = run_capture(cmd, cwd=workspace, timeout_sec=timeout_sec)
        ok = captured["returncode"] == 0 and not captured.get("timed_out", False)
        if ok:
            passed += 1
        else:
            failed += 1
        print(
            f"[slice] fail_to_pass instance={row.get('instance_id')} "
            f"test={test_name} rc={captured['returncode']} timeout={captured.get('timed_out', False)}"
        )
        results.append(
            {
                "test": test_name,
                "cmd": shlex.join(cmd),
                "returncode": captured["returncode"],
                "timed_out": captured.get("timed_out", False),
                "stdout_tail": captured["stdout"][-1200:],
                "stderr_tail": captured["stderr"][-1200:],
            }
        )

    return {
        "status": "passed" if failed == 0 else "fail_to_pass_failed",
        "total": len(fail_tests),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def resolve_active_api_key(model_name: str | None) -> tuple[str | None, str | None]:
    cli_overrides = {"active": {"model": model_name}} if model_name else None
    models_config = ModelsLoader(workspace_root=Path.cwd()).load(cli_overrides=cli_overrides)
    active_model = models_config.active.model if models_config.active else model_name
    provider_name = models_config.active.provider if models_config.active else None
    if active_model:
        try:
            _, overrides = models_config.resolve_model(active_model)
            provider_name = overrides.get("model_provider") or provider_name
        except Exception:
            pass
    if provider_name:
        provider_cfg = models_config.get_provider(provider_name)
        if provider_cfg and provider_cfg.api_key:
            return provider_cfg.api_key, provider_name
    return models_config.get_api_key(), provider_name


def snapshot_sqlite_db(source_db: Path, snapshot_db: Path) -> None:
    if not source_db.exists():
        raise RuntimeError(f"source trace db not found: {source_db}")
    snapshot_db.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_db.exists():
        snapshot_db.unlink()
    src = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    dst = sqlite3.connect(str(snapshot_db))
    try:
        # @@@trace-db-isolation - copy shared trace DB to run-local snapshot so reporting never holds locks on the live DB.
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _msg_text(msg: Any) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text", "")))
        return "".join(texts)
    return str(content)


def _collect_agent_message_texts(agent_result: Any) -> list[str]:
    if not isinstance(agent_result, dict):
        return []
    messages = agent_result.get("messages")
    if not isinstance(messages, list):
        return []
    texts: list[str] = []
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                block_texts: list[str] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block_texts.append(str(block.get("text", "")))
                if block_texts:
                    texts.append("".join(block_texts))
        else:
            text = _msg_text(msg)
            if text:
                texts.append(text)
    return texts


def _extract_agent_messages(agent_result: Any) -> list[Any]:
    if not isinstance(agent_result, dict):
        return []
    messages = agent_result.get("messages")
    if not isinstance(messages, list):
        return []
    return messages


def _message_text(msg: Any) -> str:
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            return "".join(parts)
        return str(content)
    return _msg_text(msg)


def _count_invalid_tool_calls(messages: list[Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for msg in messages:
        text = _message_text(msg)
        if not text:
            continue
        match = INVALID_TOOL_MESSAGE_RE.search(text)
        if not match:
            continue
        counter[match.group(1).lower()] += 1
    return counter


def extract_localization_candidates(agent_result: Any) -> list[str]:
    def _normalize_python_path_token(raw: str) -> str | None:
        # @@@localization-token-normalize - normalize path-like tokens and drop noisy pseudo-filenames before frequency ranking.
        normalized = raw.strip("`'\"()[]{}<>:,;").replace("\\", "/").lower()
        if not normalized.endswith(".py"):
            return None
        if (
            "site-packages" in normalized
            or ".local/lib" in normalized
            or "/venv/" in normalized
            or "/dist-packages/" in normalized
        ):
            return None
        workspace_match = re.search(r"/workspaces/[^/]+/(.+\.py)$", normalized)
        if workspace_match:
            normalized = workspace_match.group(1)
        base = normalized.rsplit("/", 1)[-1]
        stem = base[:-3]
        if len(stem) <= 1:
            return None
        if "/" not in normalized and not re.fullmatch(r"[a-z0-9][a-z0-9._-]*\.py", normalized):
            return None
        return normalized

    counts: Counter[str] = Counter()
    # @@@localization-candidate-extract - parse all agent message text for ".py" mentions to baseline localization hit-rate.
    for text in _collect_agent_message_texts(agent_result):
        for token in re.findall(r"[A-Za-z0-9_./\\-]+\.py\b", text):
            normalized = _normalize_python_path_token(token)
            if normalized:
                counts[normalized] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _ in ranked[:3]]


def collect_trace_summary(thread_id: str, instance_id: str, db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "select checkpoint, metadata from checkpoints where thread_id=? order by rowid",
            (thread_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {
            "instance_id": instance_id,
            "thread_id": thread_id,
            "checkpoint_count": 0,
            "message_count": 0,
            "human_messages": 0,
            "ai_messages": 0,
            "tool_messages": 0,
            "tool_calls_total": 0,
            "tool_call_counter": {},
            "error_markers": {},
        }

    serde = JsonPlusSerializer()
    checkpoint_blob, metadata_blob = rows[-1]
    checkpoint = serde.loads_typed(("msgpack", checkpoint_blob))
    metadata = json.loads(metadata_blob.decode())
    messages = checkpoint.get("channel_values", {}).get("messages", [])

    tool_calls: list[str] = []
    error_markers = Counter()
    invalid_tool_counter = Counter()
    human_messages = 0
    ai_messages = 0
    tool_messages = 0
    for msg in messages:
        cls = msg.__class__.__name__
        if cls == "HumanMessage":
            human_messages += 1
        elif cls == "AIMessage":
            ai_messages += 1
            for call in getattr(msg, "tool_calls", None) or []:
                tool_calls.append(str(call.get("name", "<unknown>")))
        elif cls == "ToolMessage":
            tool_messages += 1
            text = _msg_text(msg).lower()
            # @@@invalid-tool-signal - keep invalid tool calls as structured first-class signals instead of log-only strings.
            invalid_tool_match = re.match(r"error:\s*([^\s]+)\s+is not a valid tool", text)
            if invalid_tool_match:
                invalid_name = invalid_tool_match.group(1)
                invalid_tool_counter[invalid_name] += 1
                error_markers["invalid_tool_call"] += 1
            if text.startswith("error: bash is not a valid tool"):
                error_markers["invalid_tool_bash"] += 1
            if "recursion limit of" in text:
                error_markers["recursion_limit"] += 1
            if "command failed rc=" in text:
                error_markers["command_failed"] += 1
            if "command 'python' not found" in text:
                error_markers["python_not_found"] += 1

    return {
        "instance_id": instance_id,
        "thread_id": thread_id,
        "checkpoint_count": len(rows),
        "last_step": metadata.get("step"),
        "message_count": len(messages),
        "human_messages": human_messages,
        "ai_messages": ai_messages,
        "tool_messages": tool_messages,
        "tool_calls_total": len(tool_calls),
        "tool_call_counter": dict(Counter(tool_calls)),
        "invalid_tool_counter": dict(invalid_tool_counter),
        "error_markers": dict(error_markers),
        "last_ai_message": _msg_text(next((m for m in reversed(messages) if m.__class__.__name__ == "AIMessage"), ""))[
            :300
        ].replace("\n", " "),
    }


async def run_instance(
    row: dict[str, Any],
    repo_cache_root: Path,
    workspaces_root: Path,
    timeout_sec: int,
    git_timeout_sec: int,
    recursion_limit: int,
    keep_worktree: bool,
    thread_id: str,
    prompt_profile: str,
    model_name: str | None,
) -> dict[str, Any]:
    instance_id = row["instance_id"]
    repo = row["repo"]
    base_commit = row["base_commit"]
    print(f"[slice] start {instance_id} repo={repo} commit={base_commit}")

    repo_cache = ensure_repo_cache(repo, base_commit, repo_cache_root, git_timeout_sec=git_timeout_sec)
    workspace = workspaces_root / instance_id
    run(["git", "-C", str(repo_cache), "worktree", "prune"], timeout_sec=git_timeout_sec)
    if workspace.exists():
        try:
            run(["git", "-C", str(repo_cache), "worktree", "remove", "--force", str(workspace)], timeout_sec=git_timeout_sec)
        except Exception:
            shutil.rmtree(workspace)

    # @@@git-worktree-lifecycle - worktree gives clean per-instance state without recloning full repo each run.
    run(["git", "-C", str(repo_cache), "worktree", "add", "--detach", str(workspace), base_commit], timeout_sec=git_timeout_sec)
    agent: LeonAgent | None = None
    try:
        prompt = build_prompt(row, prompt_profile=prompt_profile)
        # @@@model-empty-override - empty CLI value must not override active model config.
        agent = LeonAgent(workspace_root=workspace, model_name=(model_name or None))
        if getattr(agent, "_needs_async_init", False):
            await agent.ainit()
        set_current_thread_id(thread_id)
        agent_result = await asyncio.wait_for(
            agent.agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit},
            ),
            timeout=timeout_sec,
        )
        base_messages = _extract_agent_messages(agent_result)
        invalid_calls_before = _count_invalid_tool_calls(base_messages)
        invalid_calls_after = Counter()
        correction_round_attempted = False
        if invalid_calls_before:
            # @@@invalid-tool-correction-round - explicit one-shot correction round; if still invalid, fail loudly instead of silent fallback.
            correction_round_attempted = True
            print(f"[slice] invalid_tool_detected {instance_id}: {dict(invalid_calls_before)}")
            correction_prompt = (
                "Tool contract violation detected in this thread. "
                "Use `run_command` for shell execution and do not call a tool named `bash`. "
                "Continue from current state and finish the task."
            )
            repaired_result = await asyncio.wait_for(
                agent.agent.ainvoke(
                    {"messages": [{"role": "user", "content": correction_prompt}]},
                    config={"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit},
                ),
                timeout=timeout_sec,
            )
            repaired_messages = _extract_agent_messages(repaired_result)
            if len(repaired_messages) >= len(base_messages):
                delta_messages = repaired_messages[len(base_messages) :]
            else:
                delta_messages = repaired_messages
            invalid_calls_after = _count_invalid_tool_calls(delta_messages)
            if invalid_calls_after:
                raise RuntimeError(
                    f"invalid tool call persists after correction round: {dict(invalid_calls_after)}"
                )
            agent_result = repaired_result
        localization_candidates = extract_localization_candidates(agent_result)
        print(f"[slice] localization_candidates {instance_id}: {localization_candidates}")
        patch = run(["git", "-C", str(workspace), "diff"], timeout_sec=120)
        if not patch.strip():
            print(f"[slice] warning empty patch for {instance_id}")
        gate = run_fail_to_pass_gate(row=row, workspace=workspace)
        resolution_status = "resolved"
        if gate["status"] in {"fail_to_pass_failed", "parse_error"}:
            resolution_status = "unresolved"
            print(
                f"[slice] fail_to_pass_gate_unresolved {instance_id} "
                f"status={gate['status']} passed={gate['passed']}/{gate['total']}"
            )
        return {
            KEY_INSTANCE_ID: instance_id,
            KEY_MODEL: "leonai-main",
            KEY_PREDICTION: patch,
            "correction_round_attempted": correction_round_attempted,
            "invalid_tool_before_correction": dict(invalid_calls_before),
            "invalid_tool_after_correction": dict(invalid_calls_after),
            "resolution_status": resolution_status,
            "fail_to_pass_status": gate["status"],
            "fail_to_pass_summary": {
                "total": gate["total"],
                "passed": gate["passed"],
                "failed": gate["failed"],
            },
            "fail_to_pass_results": gate["results"],
            "localization_candidates": localization_candidates,
        }
    finally:
        # @@@agent-explicit-close - do deterministic cleanup to avoid lingering threads/processes after each instance.
        if agent is not None:
            agent.close()
        set_current_thread_id("")
        if keep_worktree:
            print(f"[slice] keep workspace {workspace}")
        else:
            try:
                run(
                    ["git", "-C", str(repo_cache), "worktree", "remove", "--force", "--force", str(workspace)],
                    timeout_sec=git_timeout_sec,
                )
            except Exception as cleanup_exc:
                # @@@worktree-cleanup-fallback - don't mask the real task error with cleanup failures.
                print(f"[slice] cleanup_warning {instance_id}: {cleanup_exc}")
                shutil.rmtree(workspace, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a small SWE-bench slice with LeonAgent")
    p.add_argument("--dataset", default="SWE-bench/SWE-bench_Lite")
    p.add_argument("--split", default="test")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--timeout-sec", type=int, default=900)
    p.add_argument("--git-timeout-sec", type=int, default=240)
    p.add_argument("--recursion-limit", type=int, default=60)
    p.add_argument("--eval-timeout-sec", type=int, default=10800)
    p.add_argument("--eval-retries", type=int, default=1)
    p.add_argument("--eval-timeout-multiplier", type=float, default=2.0)
    p.add_argument("--output-dir", default="artifacts/swebench")
    p.add_argument("--keep-worktree", action="store_true")
    p.add_argument("--run-id", default="")
    p.add_argument("--arm", default="A")
    p.add_argument("--model-name", default=None)
    p.add_argument("--prompt-profile", choices=["baseline", "heuristic"], default="baseline")
    p.add_argument("--thread-prefix", default="swebench")
    p.add_argument("--source-trace-db", default=str(Path.home() / ".leon" / "leon.db"))
    p.add_argument("--trace-db", default="")
    p.add_argument("--no-eval", action="store_true")
    return p.parse_args()


async def amain() -> None:
    args = parse_args()
    api_key, provider_name = resolve_active_api_key(args.model_name)
    if not api_key:
        raise RuntimeError(
            f"API key is required for active model={args.model_name or '(active)'} provider={provider_name or '(auto)'}"
        )
    # @@@provider-key-bridge - run_slice historically hard-required OPENAI_API_KEY; bridge active provider key into expected env var to avoid false startup failure.
    if provider_name == "anthropic":
        os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
    else:
        os.environ.setdefault("OPENAI_API_KEY", api_key)

    output_dir = Path(args.output_dir).resolve()
    cache_root = output_dir / "repo_cache"
    workspaces_root = output_dir / "workspaces"
    run_stamp = args.run_id or datetime.now(timezone.utc).strftime("slice-%Y%m%d-%H%M%S")
    run_dir = output_dir / run_stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    source_trace_db = Path(args.source_trace_db).expanduser().resolve()
    if not source_trace_db.exists():
        raise RuntimeError(f"source trace db not found: {source_trace_db}")
    if args.trace_db:
        trace_db = Path(args.trace_db).expanduser().resolve()
    else:
        trace_db = run_dir / "trace_snapshot.db"

    print(
        f"[slice] run_id={run_stamp} arm={args.arm} prompt_profile={args.prompt_profile} "
        f"dataset={args.dataset} split={args.split} start={args.start} count={args.count} "
        f"model_name={args.model_name or '(active)'}"
    )
    ds = load_dataset(args.dataset, split=args.split)
    rows = [ds[i] for i in range(args.start, args.start + args.count)]

    predictions: list[dict[str, Any]] = []
    trace_summaries: list[dict[str, Any]] = []
    trace_targets: list[dict[str, str]] = []
    instance_ids: list[str] = []
    errors: list[dict[str, str]] = []
    error_type_counter: Counter[str] = Counter()
    fatal_error: dict[str, str] | None = None
    requested_instances_total = len(rows)
    for row in rows:
        instance_id = str(row["instance_id"])
        thread_id = build_thread_id(args.thread_prefix, run_stamp, instance_id)
        try:
            pred = await run_instance(
                row=row,
                repo_cache_root=cache_root,
                workspaces_root=workspaces_root,
                timeout_sec=args.timeout_sec,
                git_timeout_sec=args.git_timeout_sec,
                recursion_limit=args.recursion_limit,
                keep_worktree=args.keep_worktree,
                thread_id=thread_id,
                prompt_profile=args.prompt_profile,
                model_name=args.model_name,
            )
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc()
            error_type = classify_instance_error(msg)
            # @@@slice-error-traceback - print full traceback so run failures can be attributed without guesswork.
            print(f"[slice] error {instance_id}: {msg}\n{tb}")
            errors.append(
                {
                    "instance_id": instance_id,
                    "thread_id": thread_id,
                    "error": msg,
                    "error_type": error_type,
                    "traceback": tb,
                }
            )
            error_type_counter[error_type] += 1
            pred = {
                KEY_INSTANCE_ID: instance_id,
                KEY_MODEL: "leonai-main",
                KEY_PREDICTION: "",
            }
            if error_type == "auth":
                fatal_error = {
                    "instance_id": instance_id,
                    "error_type": error_type,
                    "error": msg,
                }
        predictions.append(pred)
        instance_ids.append(str(pred[KEY_INSTANCE_ID]))
        trace_targets.append({"instance_id": instance_id, "thread_id": thread_id})
        print(f"[slice] done {pred[KEY_INSTANCE_ID]} patch_len={len(pred[KEY_PREDICTION])}")
        if fatal_error:
            print(
                f"[slice] fatal_error_stop instance={fatal_error['instance_id']} "
                f"type={fatal_error['error_type']}"
            )
            break

    # @@@trace-snapshot-once - snapshot the shared trace DB once per run to avoid O(N) full-file copies for multi-instance slices.
    if trace_targets:
        correction_meta_by_instance: dict[str, dict[str, Any]] = {}
        for pred in predictions:
            instance_id = str(pred.get(KEY_INSTANCE_ID) or "")
            if not instance_id:
                continue
            if "correction_round_attempted" not in pred:
                continue
            correction_meta_by_instance[instance_id] = {
                # @@@correction-metrics-propagation - persist correction-round counters into trace summaries so A/B can read them from artifacts, not logs.
                "correction_round_attempted": bool(pred.get("correction_round_attempted")),
                "invalid_tool_before_correction": pred.get("invalid_tool_before_correction") or {},
                "invalid_tool_after_correction": pred.get("invalid_tool_after_correction") or {},
            }
        snapshot_sqlite_db(source_db=source_trace_db, snapshot_db=trace_db)
        for target in trace_targets:
            summary = collect_trace_summary(
                thread_id=target["thread_id"],
                instance_id=target["instance_id"],
                db_path=trace_db,
            )
            summary.update(correction_meta_by_instance.get(target["instance_id"], {}))
            trace_summaries.append(summary)
            print(f"[slice] trace {target['instance_id']} checkpoints={summary.get('checkpoint_count', 0)}")

    predictions_path = run_dir / "predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as f:
        for item in predictions:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    ids_path = run_dir / "instance_ids.txt"
    ids_path.write_text("\n".join(instance_ids) + "\n", encoding="utf-8")
    trace_path = run_dir / "trace_summaries.jsonl"
    with trace_path.open("w", encoding="utf-8") as f:
        for item in trace_summaries:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[slice] predictions={predictions_path}")
    print(f"[slice] instance_ids={ids_path}")
    print(f"[slice] trace_summaries={trace_path}")
    if errors:
        errors_path = run_dir / "errors.json"
        errors_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[slice] errors={errors_path}")

    eval_summary_path = ""
    eval_error = ""
    eval_attempts: list[dict[str, Any]] = []
    if not args.no_eval:
        # @@@swebench-eval-contract - pass explicit instance ids so harness evaluates only this small slice.
        eval_cmd = [
            sys.executable,
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            args.dataset,
            "--split",
            args.split,
            "--predictions_path",
            str(predictions_path),
            "--instance_ids",
            *instance_ids,
            "--max_workers",
            "1",
            "--run_id",
            run_stamp,
            "--report_dir",
            str(run_dir),
        ]
        print(f"[slice] eval_cmd={' '.join(eval_cmd)}")
        max_attempts = max(1, int(args.eval_retries) + 1)
        timeout_now = max(1, int(args.eval_timeout_sec))
        for attempt in range(1, max_attempts + 1):
            try:
                # @@@harness-timeout-retry - automated retry keeps evaluation closure inside runner, no manual harness rerun needed.
                run(eval_cmd, timeout_sec=timeout_now)
                print(f"[slice] evaluation complete run_dir={run_dir} attempt={attempt}")
                candidate = Path.cwd() / f"leonai-main.{run_stamp}.json"
                if candidate.exists():
                    eval_summary_path = str(candidate)
                    print(f"[slice] eval_summary={candidate}")
                eval_attempts.append({"attempt": attempt, "timeout_sec": timeout_now, "status": "ok"})
                eval_error = ""
                break
            except Exception as exc:
                eval_error = str(exc)
                eval_attempts.append(
                    {
                        "attempt": attempt,
                        "timeout_sec": timeout_now,
                        "status": "error",
                        "error": eval_error,
                    }
                )
                print(f"[slice] evaluation_error attempt={attempt}: {eval_error}")
                is_timeout = "command timeout after" in eval_error
                has_next = attempt < max_attempts
                if not (is_timeout and has_next):
                    break
                timeout_now = max(timeout_now + 1, int(timeout_now * float(args.eval_timeout_multiplier)))
                print(f"[slice] evaluation_retry_next_timeout={timeout_now}")
    else:
        print("[slice] skip evaluation (--no-eval)")

    error_instance_ids = {entry["instance_id"] for entry in errors}
    empty_patch_total = sum(
        1
        for prediction in predictions
        if prediction[KEY_INSTANCE_ID] not in error_instance_ids and not prediction[KEY_PREDICTION].strip()
    )

    manifest = {
        "run_id": run_stamp,
        "arm": args.arm,
        "model_name": args.model_name,
        "prompt_profile": args.prompt_profile,
        "dataset": args.dataset,
        "split": args.split,
        "start": args.start,
        "count": args.count,
        "timeout_sec": args.timeout_sec,
        "git_timeout_sec": args.git_timeout_sec,
        "recursion_limit": args.recursion_limit,
        "thread_prefix": args.thread_prefix,
        "source_trace_db": str(source_trace_db),
        "trace_db": str(trace_db),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "instances_requested_total": requested_instances_total,
        "instances_total": len(instance_ids),
        "errors_total": len(errors),
        "error_type_counter": dict(error_type_counter),
        "empty_patch_total": empty_patch_total,
        "predictions_path": str(predictions_path),
        "instance_ids_path": str(ids_path),
        "trace_summaries_path": str(trace_path),
        "eval_summary_path": eval_summary_path,
        "eval_error": eval_error,
        "eval_attempts": eval_attempts,
        "aborted": bool(fatal_error),
        "aborted_reason": fatal_error,
    }
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[slice] manifest={manifest_path}")
    if eval_error:
        raise RuntimeError(f"evaluation failed after manifest write: {eval_error}")


if __name__ == "__main__":
    asyncio.run(amain())
