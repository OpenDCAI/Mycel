"""Run a small SWE-bench slice with LeonAgent and evaluate via official harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datasets import load_dataset
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from swebench.harness.constants import KEY_INSTANCE_ID, KEY_MODEL, KEY_PREDICTION

from agent import LeonAgent
from sandbox.thread_context import set_current_thread_id


def run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed rc={proc.returncode}\ncmd={' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


def ensure_repo_cache(repo: str, cache_root: Path) -> Path:
    repo_dir = cache_root / repo.replace("/", "__")
    if not repo_dir.exists():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", f"https://github.com/{repo}.git", str(repo_dir)])
    else:
        run(["git", "-C", str(repo_dir), "fetch", "--all", "--prune"])
    return repo_dir


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
                "Execution constraints:",
                "- Use tool name `run_command` instead of `bash`.",
                "- Use `python3` instead of `python` in commands.",
                "- If you already changed files and validated key tests, stop and summarize.",
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
    recursion_limit: int,
    keep_worktree: bool,
    thread_id: str,
    prompt_profile: str,
) -> dict[str, Any]:
    instance_id = row["instance_id"]
    repo = row["repo"]
    base_commit = row["base_commit"]
    print(f"[slice] start {instance_id} repo={repo} commit={base_commit}")

    repo_cache = ensure_repo_cache(repo, repo_cache_root)
    workspace = workspaces_root / instance_id
    run(["git", "-C", str(repo_cache), "worktree", "prune"])
    if workspace.exists():
        try:
            run(["git", "-C", str(repo_cache), "worktree", "remove", "--force", str(workspace)])
        except Exception:
            shutil.rmtree(workspace)

    # @@@git-worktree-lifecycle - worktree gives clean per-instance state without recloning full repo each run.
    run(["git", "-C", str(repo_cache), "worktree", "add", "--detach", str(workspace), base_commit])
    try:
        prompt = build_prompt(row, prompt_profile=prompt_profile)
        agent = LeonAgent(workspace_root=workspace)
        if getattr(agent, "_needs_async_init", False):
            await agent.ainit()
        set_current_thread_id(thread_id)
        await asyncio.wait_for(
            agent.agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit},
            ),
            timeout=timeout_sec,
        )
        patch = run(["git", "-C", str(workspace), "diff"])
        if not patch.strip():
            print(f"[slice] warning empty patch for {instance_id}")
        return {
            KEY_INSTANCE_ID: instance_id,
            KEY_MODEL: "leonai-main",
            KEY_PREDICTION: patch,
        }
    finally:
        if keep_worktree:
            print(f"[slice] keep workspace {workspace}")
        else:
            run(["git", "-C", str(repo_cache), "worktree", "remove", "--force", str(workspace)])


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run a small SWE-bench slice with LeonAgent")
    p.add_argument("--dataset", default="SWE-bench/SWE-bench_Lite")
    p.add_argument("--split", default="test")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--timeout-sec", type=int, default=900)
    p.add_argument("--recursion-limit", type=int, default=60)
    p.add_argument("--output-dir", default="artifacts/swebench")
    p.add_argument("--keep-worktree", action="store_true")
    p.add_argument("--run-id", default="")
    p.add_argument("--arm", default="A")
    p.add_argument("--prompt-profile", choices=["baseline", "heuristic"], default="baseline")
    p.add_argument("--thread-prefix", default="swebench")
    p.add_argument("--source-trace-db", default=str(Path.home() / ".leon" / "leon.db"))
    p.add_argument("--trace-db", default="")
    p.add_argument("--no-eval", action="store_true")
    return p.parse_args()


async def amain() -> None:
    args = parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required")

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
        f"dataset={args.dataset} split={args.split} start={args.start} count={args.count}"
    )
    ds = load_dataset(args.dataset, split=args.split)
    rows = [ds[i] for i in range(args.start, args.start + args.count)]

    predictions: list[dict[str, Any]] = []
    trace_summaries: list[dict[str, Any]] = []
    instance_ids: list[str] = []
    errors: list[dict[str, str]] = []
    for row in rows:
        instance_id = str(row["instance_id"])
        thread_id = build_thread_id(args.thread_prefix, run_stamp, instance_id)
        try:
            pred = await run_instance(
                row=row,
                repo_cache_root=cache_root,
                workspaces_root=workspaces_root,
                timeout_sec=args.timeout_sec,
                recursion_limit=args.recursion_limit,
                keep_worktree=args.keep_worktree,
                thread_id=thread_id,
                prompt_profile=args.prompt_profile,
            )
        except Exception as exc:
            msg = str(exc)
            print(f"[slice] error {instance_id}: {msg}")
            errors.append({"instance_id": instance_id, "thread_id": thread_id, "error": msg})
            pred = {
                KEY_INSTANCE_ID: instance_id,
                KEY_MODEL: "leonai-main",
                KEY_PREDICTION: "",
            }
        predictions.append(pred)
        instance_ids.append(str(pred[KEY_INSTANCE_ID]))

        snapshot_sqlite_db(source_db=source_trace_db, snapshot_db=trace_db)
        summary = collect_trace_summary(thread_id=thread_id, instance_id=instance_id, db_path=trace_db)
        trace_summaries.append(summary)
        print(
            f"[slice] done {pred[KEY_INSTANCE_ID]} patch_len={len(pred[KEY_PREDICTION])} "
            f"checkpoints={summary.get('checkpoint_count', 0)}"
        )

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
    if not args.no_eval:
        # @@@swebench-eval-contract - pass explicit instance ids so harness evaluates only this small slice.
        eval_cmd = [
            "python3",
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
        run(eval_cmd)
        print(f"[slice] evaluation complete run_dir={run_dir}")
        candidate = Path.cwd() / f"leonai-main.{run_stamp}.json"
        if candidate.exists():
            eval_summary_path = str(candidate)
            print(f"[slice] eval_summary={candidate}")
    else:
        print("[slice] skip evaluation (--no-eval)")

    manifest = {
        "run_id": run_stamp,
        "arm": args.arm,
        "prompt_profile": args.prompt_profile,
        "dataset": args.dataset,
        "split": args.split,
        "start": args.start,
        "count": args.count,
        "timeout_sec": args.timeout_sec,
        "recursion_limit": args.recursion_limit,
        "thread_prefix": args.thread_prefix,
        "source_trace_db": str(source_trace_db),
        "trace_db": str(trace_db),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "instances_total": len(instance_ids),
        "errors_total": len(errors),
        "empty_patch_total": sum(1 for p in predictions if not p[KEY_PREDICTION].strip()),
        "predictions_path": str(predictions_path),
        "instance_ids_path": str(ids_path),
        "trace_summaries_path": str(trace_path),
        "eval_summary_path": eval_summary_path,
    }
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[slice] manifest={manifest_path}")


if __name__ == "__main__":
    asyncio.run(amain())
