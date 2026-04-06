# Model Error Recovery Strategy Chain Design

**Date:** 2026-04-07
**Branch:** `dev`

## Goal

Refactor `QueryLoop._handle_model_error_recovery(...)` into an explicit strategy chain without changing current recovery behavior.

This slice is about structure and ownership, not new recovery policy.

## Scope

This design covers:

- `core/runtime/loop.py`
- focused `tests/Unit/core/test_loop.py` coverage for model-error recovery ordering
- one narrow loop integration seed that proves the same caller-visible behavior after the refactor

This design does **not** cover:

- `QueryLoop._handle_truncated_response_recovery(...)`
- new recovery strategies
- prompt/message wording changes
- middleware compaction semantics
- model/provider error taxonomy expansion

## Current Facts

### 1. `_handle_model_error_recovery(...)` already owns multiple distinct strategies

Current `core/runtime/loop.py` mixes these branches in one method:

1. parsed context-overflow override
2. transient API retry
3. `max_output_tokens` escalation / continuation recovery
4. prompt-too-long collapse-drain
5. prompt-too-long reactive compact
6. prompt-too-long terminal exhaustion

The method is still coherent, but it is no longer small.

### 2. Existing tests already encode the contract

Current focused unit tests prove the expected ordering:

- parsed overflow produces targeted `max_output_tokens_override`
- transient 429/529 retries happen before terminal failure
- max-output escalation happens before continuation recovery
- prompt-too-long tries collapse-drain once before reactive compact
- prompt-too-long surfaces a terminal notice after recovery exhausts

This means the refactor has a real behavioral bar already. The work is not to invent new tests; it is to preserve the existing contract while making the strategy boundaries explicit.

### 3. Truncated-response recovery is adjacent but separate

`_handle_truncated_response_recovery(...)` shares some ideas with `_handle_model_error_recovery(...)`, but it is a different caller surface:

- it runs on an `AIMessage`
- it reacts to finish reasons, not raised exceptions
- it decides whether to yield the truncated assistant message

It should stay out of this slice. Pulling both into one refactor would turn a bounded seam into a runtime-wide rewrite.

## Problem

Right now `_handle_model_error_recovery(...)` is still one interleaved method.

That has three costs:

- adding or reordering one recovery branch requires re-reading the entire method
- the actual recovery ordering is implicit in `if` nesting instead of being named
- unit tests cannot target one strategy boundary without going through the whole method body

The current code works, but the boundary owner is still muddy.

## Chosen Approach

Keep `_handle_model_error_recovery(...)` as the public coordinator, but move each branch into a named strategy helper and run them through one explicit chain.

Recommended shape:

- add one small immutable error context object carrying the current inputs
- add one ordered list/tuple of strategy callables
- make `_handle_model_error_recovery(...)` iterate that chain until a strategy returns a result

This keeps the same entrypoint and return type while making the ordering explicit.

## Intended Strategy Order

The chain should preserve the current policy exactly:

1. context-overflow parse -> targeted `max_output_tokens_override`
2. transient API retry
3. max-output-token recovery
4. prompt-too-long collapse-drain
5. prompt-too-long reactive compact
6. prompt-too-long terminal exhaustion

Important: the last three are still one conceptual lane, but the first two recovery attempts should become separate strategies so their ordering is visible and individually testable.

## Intended Backend Shape

### Keep one typed result object

Continue returning `_ModelErrorRecoveryResult | None`.

Do not replace it with ad-hoc dicts or tuples. The typed result is already the honest contract here.

### Add one context carrier

Add a small dataclass, for example:

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

This avoids re-threading the same argument list through every helper.

### Add named strategy helpers

Recommended helper split:

- `_try_context_overflow_escalate(ctx)`
- `_try_transient_api_retry(ctx)`
- `_try_max_output_tokens_recovery(ctx)`
- `_try_prompt_too_long_collapse_drain(ctx)`
- `_try_prompt_too_long_reactive_compact(ctx)`
- `_terminal_prompt_too_long_exhaustion(ctx)`

The last helper may still be terminal-only rather than “try” shaped, but it should remain part of the prompt-too-long lane rather than becoming a generic fallback.

### Coordinator stays small

After the split, `_handle_model_error_recovery(...)` should do only three things:

1. build context
2. iterate strategy helpers in order
3. return the first non-`None` result

That keeps the public method stable while making the policy readable.

## Non-Goals

- Do not merge `_handle_model_error_recovery(...)` with `_handle_truncated_response_recovery(...)`
- Do not invent a reusable “strategy framework” outside `loop.py`
- Do not move recovery logic into middleware
- Do not change notice text, retry counts, or token constants in this slice

## Testing Strategy

### Required proof

- keep current unit tests green
- add one focused red/green test that proves `_handle_model_error_recovery(...)` now delegates through an explicit strategy sequence instead of one monolith
- keep one loop integration seed green to show caller-visible behavior did not drift

### Good proof candidates

- `tests/Unit/core/test_loop.py::test_handle_model_error_recovery_returns_typed_result_object`
- prompt-too-long collapse/reactive tests already in the file
- `tests/Integration/test_query_loop_backend_bridge.py -k 'tags_display_delta_with_source_seq'` as a cheap loop-adjacent regression seed

### Out-of-scope failures

If a `LeonAgent` integration test fails earlier on missing Supabase env, that is not evidence against this checkpoint. Record it honestly and keep it separate.

## Stopline

This slice stops when:

- `_handle_model_error_recovery(...)` becomes an explicit strategy coordinator
- recovery ordering is named and preserved
- focused unit coverage remains green
- one loop-adjacent integration seed remains green

It must **not** expand into:

- truncated-response refactors
- new retry policies
- model/provider env bringup cleanup
- generic runtime architecture surgery
