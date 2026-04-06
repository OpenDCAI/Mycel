# Model Error Recovery Strategy Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `QueryLoop._handle_model_error_recovery(...)` into an explicit strategy chain while preserving current recovery behavior.

**Architecture:** Keep `_handle_model_error_recovery(...)` as the stable coordinator. Introduce one small context dataclass plus a fixed strategy sequence inside `core/runtime/loop.py`, then move each current branch into a named helper without touching `_handle_truncated_response_recovery(...)`.

**Tech Stack:** Python, asyncio, pytest, pyright, ruff

---

### Task 1: Lock the coordinator seam with a failing test

**Files:**
- Modify: `tests/Unit/core/test_loop.py`
- Read: `core/runtime/loop.py`

- [ ] **Step 1: Write the failing test**

Add one unit that forces `_handle_model_error_recovery(...)` to run through an explicit strategy list instead of one private monolith. Keep it narrow by monkeypatching named helpers on `QueryLoop`.

Expected shape:

```python
@pytest.mark.asyncio
async def test_handle_model_error_recovery_uses_ordered_strategy_chain(monkeypatch):
    loop = make_loop(mock_model_no_tools(), app_state=AppState(), runtime=SimpleNamespace(cost=0.0))
    calls: list[str] = []

    async def first(_ctx):
        calls.append("first")
        return None

    async def second(_ctx):
        calls.append("second")
        return _ModelErrorRecoveryResult(...)

    monkeypatch.setattr(loop, "_model_error_recovery_strategies", lambda: (first, second))

    result = await loop._handle_model_error_recovery(...)

    assert calls == ["first", "second"]
    assert result is not None
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
uv run pytest tests/Unit/core/test_loop.py -k 'test_handle_model_error_recovery_uses_ordered_strategy_chain' -q
```

Expected: FAIL because `QueryLoop` does not yet expose an ordered strategy seam.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/Unit/core/test_loop.py
git commit -m "test: cover model error recovery strategy chain"
```

### Task 2: Introduce the context object and coordinator seam

**Files:**
- Modify: `core/runtime/loop.py`
- Modify: `tests/Unit/core/test_loop.py`

- [ ] **Step 1: Add a context dataclass**

In `core/runtime/loop.py`, add a small immutable context object near `_ModelErrorRecoveryResult`:

```python
@dataclass(frozen=True)
class _ModelErrorContext:
    exc: Exception
    error_text: str
    thread_id: str
    messages: list
    turn: int
    transition: ContinueState | None
    max_output_tokens_recovery_count: int
    has_attempted_reactive_compact: bool
    max_output_tokens_override: int | None
    transient_api_retry_count: int
```

- [ ] **Step 2: Add a strategy list seam**

Add a tiny builder method on `QueryLoop`:

```python
def _model_error_recovery_strategies(self):
    return (
        self._try_context_overflow_escalate,
        self._try_transient_api_retry,
        self._try_max_output_tokens_recovery,
        self._try_prompt_too_long_collapse_drain,
        self._try_prompt_too_long_reactive_compact,
        self._try_prompt_too_long_terminal,
    )
```

- [ ] **Step 3: Rewrite `_handle_model_error_recovery(...)` as coordinator only**

Keep the public signature and return type unchanged. Internally:

1. build `_ModelErrorContext`
2. iterate `self._model_error_recovery_strategies()`
3. return the first non-`None` result
4. otherwise return `None`

- [ ] **Step 4: Run the focused unit**

Run:

```bash
uv run pytest tests/Unit/core/test_loop.py -k 'test_handle_model_error_recovery_uses_ordered_strategy_chain or test_handle_model_error_recovery_returns_typed_result_object' -q
```

Expected: PASS

- [ ] **Step 5: Commit the coordinator seam**

```bash
git add core/runtime/loop.py tests/Unit/core/test_loop.py
git commit -m "refactor: extract model error recovery coordinator"
```

### Task 3: Move each current branch into named helpers

**Files:**
- Modify: `core/runtime/loop.py`
- Modify: `tests/Unit/core/test_loop.py`

- [ ] **Step 1: Extract the first three independent helpers**

Move current logic into:

- `_try_context_overflow_escalate(ctx)`
- `_try_transient_api_retry(ctx)`
- `_try_max_output_tokens_recovery(ctx)`

Each helper should return `_ModelErrorRecoveryResult | None` and preserve current constants, messages, and retry counts.

- [ ] **Step 2: Extract the prompt-too-long lane as three helpers**

Move current prompt-too-long logic into:

- `_try_prompt_too_long_collapse_drain(ctx)`
- `_try_prompt_too_long_reactive_compact(ctx)`
- `_try_prompt_too_long_terminal(ctx)`

Keep the current single-shot collapse-drain behavior and the current reactive-compact exhaustion semantics unchanged.

- [ ] **Step 3: Keep `_handle_truncated_response_recovery(...)` untouched**

Do not modify that method in this task.

- [ ] **Step 4: Run the existing recovery pack**

Run:

```bash
uv run pytest tests/Unit/core/test_loop.py -k 'max_output_tokens or prompt_too_long or transient or context_overflow or handle_model_error_recovery' -q
```

Expected: PASS

- [ ] **Step 5: Commit the helper extraction**

```bash
git add core/runtime/loop.py tests/Unit/core/test_loop.py
git commit -m "refactor: split model error recovery strategies"
```

### Task 4: Prove no loop-level behavior drift

**Files:**
- Read: `tests/Integration/test_query_loop_backend_bridge.py`
- Modify: `tests/Unit/core/test_loop.py` only if one extra assertion is still needed

- [ ] **Step 1: Keep one loop-adjacent integration seed green**

Run:

```bash
uv run pytest tests/Integration/test_query_loop_backend_bridge.py -k 'tags_display_delta_with_source_seq' -q
```

Expected: PASS

- [ ] **Step 2: Run touched static checks**

Run:

```bash
uv run pyright core/runtime/loop.py tests/Unit/core/test_loop.py
uv run ruff check core/runtime/loop.py tests/Unit/core/test_loop.py
uv run ruff format --check core/runtime/loop.py tests/Unit/core/test_loop.py
```

Expected: `0 errors` from pyright, all green from ruff/format.

- [ ] **Step 3: Record the out-of-scope env-dependent seed honestly**

Optionally re-run:

```bash
uv run pytest tests/Integration/test_leon_agent.py -k 'astream_messages_updates_mode_yields_langgraph_tuples' -q
```

If it still fails at missing Supabase env during agent init, record that as unrelated bringup debt. Do not “fix it while here.”

- [ ] **Step 4: Commit the completed checkpoint**

```bash
git add core/runtime/loop.py tests/Unit/core/test_loop.py
git commit -m "refactor: turn model error recovery into strategy chain"
```
