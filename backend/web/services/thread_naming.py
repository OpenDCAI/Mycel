"""Canonical thread naming helpers."""

from __future__ import annotations


def validate_thread_identity(*, is_main: bool, branch_index: int) -> None:
    if branch_index < 0:
        raise ValueError(f"branch_index must be >= 0, got {branch_index}")
    if is_main and branch_index != 0:
        raise ValueError(f"Default thread must have branch_index=0, got {branch_index}")
    if not is_main and branch_index == 0:
        raise ValueError("Child thread must have branch_index>0")


def sidebar_label(*, is_main: bool, branch_index: int) -> str | None:
    validate_thread_identity(is_main=is_main, branch_index=branch_index)
    if is_main:
        return None
    return f"分身{branch_index}"
