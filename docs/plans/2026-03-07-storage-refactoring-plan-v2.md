# Storage Layer Refactoring - Implementation Plan v2

**Date:** 2026-03-07
**Branch:** refactor/storage-layer-separation
**Scope:** Extract 66 SQL operations from 7 sandbox files into unified storage layer
**Strategy:** Branch by Abstraction + Strangler Fig + Parallel Change

---

## Executive Summary

**Problem:** Sandbox domain layer has direct SQLite dependencies, violating separation of concerns.

**Solution:** Use **Branch by Abstraction** pattern to safely migrate to unified `SandboxRepository`.

**Key Insight:** Don't refactor directly. Create abstraction layer first, run both implementations in parallel, migrate incrementally, then remove old code.

**Effort:** 8-12 hours (4 phases)
**Risk:** Medium (was High, now reduced via parallel change)
**Approach:** Abstraction → Implementation → Migration → Cleanup

---

## Architectural Patterns Applied

### 1. Branch by Abstraction
Create interface, implement both old and new behind it, switch callers, remove old.

### 2. Strangler Fig
New repository gradually replaces old SQL code while both coexist.

### 3. Parallel Change (Expand-Contract)
- **Expand:** Add repository alongside existing SQL
- **Migrate:** Update callers one by one
- **Contract:** Remove old SQL

### 4. Repository Pattern Best Practices
- Protocol-based interface (duck typing)
- Explicit transaction boundaries
- Return domain objects, not raw dicts
- Single responsibility per method
- No storage leakage to domain

---

## Phase 0: Characterization & Abstraction (2-3 hours)

**Goal:** Capture current behavior, create abstraction layer, NO behavior change.

### 0.1 Characterization Tests

**Purpose:** Document current behavior BEFORE refactoring.

**Task:** Write tests that capture exact current behavior of SQL operations.

```python
# tests/sandbox/test_lease_characterization.py
"""Characterization tests for lease persistence.

These tests document CURRENT behavior (including quirks/bugs).
They serve as regression detection during refactoring.
"""

def test_lease_creation_current_behavior():
    """Document exact behavior of current lease creation."""
    # Create lease using current SQLiteLease
    # Capture all side effects (DB state, return values, exceptions)
    pass

def test_lease_state_transition_current_behavior():
    """Document exact state machine behavior."""
    pass
```

**Deliverable:** Characterization test suite for all 7 files.

### 0.2 Extract Table Schemas

**Task:** Document all table schemas from CREATE TABLE statements.

**Files:**
- `sandbox/lease.py` → sandbox_leases, sandbox_instances, lease_events
- `sandbox/terminal.py` → abstract_terminals, thread_terminal_pointers
- `sandbox/chat_session.py` → chat_sessions, terminal_commands, terminal_command_chunks
- `sandbox/runtime.py`, `provider_events.py`, `manager.py`, `capability.py`

**Deliverable:** `docs/architecture/sandbox-schema.md` with all table definitions.

### 0.3 Design Repository Protocol

**File:** `storage/providers/sqlite/sandbox_repository_protocol.py`

```python
"""Repository protocol for sandbox persistence.

This protocol defines the contract that both legacy and new implementations must satisfy.
"""

from typing import Protocol, Any
from pathlib import Path

class SandboxRepositoryProtocol(Protocol):
    """Protocol for sandbox persistence operations."""

    # Lease operations
    def upsert_lease(self, lease_id: str, **kwargs) -> None: ...
    def get_lease(self, lease_id: str) -> dict[str, Any] | None: ...
    def update_lease_state(self, lease_id: str, observed_state: str, **kwargs) -> None: ...
    def delete_lease(self, lease_id: str) -> None: ...

    # Instance operations
    def upsert_instance(self, instance_id: str, lease_id: str, **kwargs) -> None: ...
    def get_instance(self, instance_id: str) -> dict[str, Any] | None: ...

    # Terminal operations
    def upsert_terminal(self, terminal_id: str, **kwargs) -> None: ...
    def get_terminal(self, terminal_id: str) -> dict[str, Any] | None: ...
    def delete_terminal(self, terminal_id: str) -> None: ...

    # Session operations
    def upsert_session(self, session_id: str, **kwargs) -> None: ...
    def get_session(self, session_id: str) -> dict[str, Any] | None: ...
    def update_session_status(self, session_id: str, status: str) -> None: ...

    # Event operations
    def insert_lease_event(self, event_id: str, lease_id: str, **kwargs) -> None: ...
```

**Deliverable:** Protocol definition with all required methods.

### 0.4 Create Legacy Adapter

**File:** `storage/providers/sqlite/legacy_sandbox_repository.py`

**Purpose:** Wrap existing inline SQL code behind repository protocol.

```python
"""Legacy adapter wrapping existing inline SQL.

This adapter delegates to the EXISTING SQL code in sandbox/*.py files.
It provides a repository interface without changing behavior.
"""

class LegacySandboxRepository:
    """Adapter wrapping existing inline SQL operations."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def upsert_lease(self, lease_id: str, **kwargs) -> None:
        # Delegate to existing SQLiteLease._upsert_snapshot()
        # NO new code, just wrapping existing
        pass
```

**Key principle:** This adapter calls EXISTING code. No new SQL. Just wrapping.

**Deliverable:** Legacy adapter that passes characterization tests.

### 0.5 Contract Tests

**File:** `tests/storage/test_sandbox_repository_contract.py`

**Purpose:** Define repository contract that both implementations must satisfy.

```python
"""Contract tests for SandboxRepository implementations.

These tests run against BOTH legacy and new implementations
to prove behavioral equivalence.
"""

import pytest

@pytest.fixture(params=["legacy", "new"])
def repository(request):
    """Parametrized fixture providing both implementations."""
    if request.param == "legacy":
        return LegacySandboxRepository()
    else:
        return SandboxRepository()

def test_lease_creation_contract(repository):
    """Both implementations must create leases identically."""
    # Test against protocol, not implementation
    pass

def test_lease_state_transition_contract(repository):
    """Both implementations must handle state transitions identically."""
    pass
```

**Deliverable:** Contract test suite that both implementations must pass.

**Commit:** `refactor(storage): add repository protocol and legacy adapter`

---

## Phase 1: New Repository Implementation (2-3 hours)

**Goal:** Implement new repository conforming to protocol, prove equivalence.

### 1.1 Implement SandboxRepository

**File:** `storage/providers/sqlite/sandbox_repo.py`

**Structure:**
```python
"""New unified repository for sandbox persistence."""

class SandboxRepository:
    """Clean implementation of sandbox persistence."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # Context manager for explicit transactions
    def __enter__(self):
        self._conn = connect_sqlite(self.db_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        self._conn = None

    # Lease operations
    def upsert_lease(self, lease_id: str, **kwargs) -> None:
        """Insert or update lease."""
        # Clean SQL implementation
        pass
```

**Key improvements over inline SQL:**
- Explicit transaction boundaries (context manager)
- Connection pooling/reuse
- Consistent error handling
- Type hints
- Docstrings

**Implementation order:**
1. Connection management + transactions
2. Table creation (ensure_tables)
3. Lease operations
4. Instance operations
5. Terminal operations
6. Session operations
7. Event operations

### 1.2 Run Contract Tests

**Task:** Verify new repository passes all contract tests.

```bash
# Run contract tests against both implementations
pytest tests/storage/test_sandbox_repository_contract.py -v

# Should see:
# test_lease_creation_contract[legacy] PASSED
# test_lease_creation_contract[new] PASSED
```

**Success criteria:** All contract tests pass for both implementations.

### 1.3 Performance Comparison

**Task:** Benchmark both implementations to detect regressions.

```python
# tests/storage/benchmark_repository.py
"""Performance comparison between legacy and new."""

def benchmark_lease_creation(repository, n=1000):
    start = time.time()
    for i in range(n):
        repository.upsert_lease(f"lease-{i}", ...)
    return time.time() - start

# Run against both, compare
```

**Deliverable:** Performance report showing new implementation is comparable or faster.

**Commit:** `refactor(storage): implement new SandboxRepository`

---

## Phase 2: Parallel Migration (3-4 hours)

**Goal:** Migrate callers to use repository interface, keep both implementations working.

### 2.1 Add Dependency Injection

**File:** `sandbox/config.py`

```python
"""Sandbox configuration with repository injection."""

# Feature flag for gradual rollout
USE_NEW_REPOSITORY = os.getenv("LEON_USE_NEW_REPOSITORY", "false").lower() == "true"

def get_sandbox_repository() -> SandboxRepositoryProtocol:
    """Factory for repository implementation."""
    if USE_NEW_REPOSITORY:
        from storage.providers.sqlite.sandbox_repo import SandboxRepository
        return SandboxRepository()
    else:
        from storage.providers.sqlite.legacy_sandbox_repository import LegacySandboxRepository
        return LegacySandboxRepository()
```

**Key benefit:** Switch implementations via environment variable, no code changes.

### 2.2 Migrate lease.py (17 ops)

**Strategy:** Replace inline SQL with repository calls, keep domain logic.

**Before:**
```python
class SQLiteLease(SandboxLease):
    def _upsert_snapshot(self):
        with _connect(self._db_path) as conn:
            conn.execute("INSERT INTO sandbox_leases ...")
```

**After:**
```python
class SQLiteLease(SandboxLease):
    def __init__(self, ..., repository: SandboxRepositoryProtocol | None = None):
        self._repository = repository or get_sandbox_repository()

    def _upsert_snapshot(self):
        self._repository.upsert_lease(self.lease_id, ...)
```

**Testing:**
```bash
# Test with legacy implementation (default)
pytest tests/sandbox/test_lease.py -v

# Test with new implementation
LEON_USE_NEW_REPOSITORY=true pytest tests/sandbox/test_lease.py -v

# Both should pass
```

**Commit:** `refactor(lease): migrate to repository interface`

### 2.3 Migrate terminal.py (19 ops)

**Same strategy:** Replace SQL with repository calls, inject dependency.

**Commit:** `refactor(terminal): migrate to repository interface`

### 2.4 Migrate chat_session.py (10 ops)

**Commit:** `refactor(session): migrate to repository interface`

### 2.5 Migrate remaining files

- runtime.py (10 ops)
- provider_events.py (5 ops)
- manager.py (4 ops)
- capability.py (1 op)

**Commit after each:** `refactor(<file>): migrate to repository interface`

### 2.6 Gradual Rollout Strategy

**Option A: Per-entity rollout**
```python
USE_NEW_REPO_LEASES = os.getenv("LEON_NEW_REPO_LEASES", "false") == "true"
USE_NEW_REPO_TERMINALS = os.getenv("LEON_NEW_REPO_TERMINALS", "false") == "true"
```

**Option B: Percentage rollout**
```python
NEW_REPO_PERCENTAGE = int(os.getenv("LEON_NEW_REPO_PCT", "0"))
use_new = random.randint(0, 100) < NEW_REPO_PERCENTAGE
```

**Recommendation:** Start with 0%, gradually increase to 100%.

---

## Phase 3: Contract & Cleanup (2-3 hours)

**Goal:** Remove old implementation, clean up feature flags.

### 3.1 Verify All Tests Pass with New Repository

```bash
# Force new repository for all tests
LEON_USE_NEW_REPOSITORY=true pytest tests/ -v

# All tests should pass
```

### 3.2 Remove Legacy Adapter

**Task:** Delete `legacy_sandbox_repository.py` and all inline SQL from sandbox files.

**Files to clean:**
- Remove SQL from lease.py, terminal.py, chat_session.py, etc.
- Remove `_connect()` helpers
- Remove `import sqlite3`

**Verification:**
```bash
# Should return no results
grep -r "import sqlite3" sandbox/*.py
grep -r "CREATE TABLE" sandbox/*.py
grep -r "INSERT INTO" sandbox/*.py
```

### 3.3 Remove Feature Flags

**Task:** Remove `USE_NEW_REPOSITORY` flag, always use new implementation.

```python
# Before
def get_sandbox_repository():
    if USE_NEW_REPOSITORY:
        return SandboxRepository()
    else:
        return LegacySandboxRepository()

# After
def get_sandbox_repository():
    return SandboxRepository()
```

### 3.4 Update Documentation

**Files:**
- `docs/architecture/storage-layer.md` - Document repository pattern
- `docs/architecture/sandbox-schema.md` - Update with final schema
- `MEMORY.md` - Add refactoring notes

### 3.5 Final Verification

```bash
# Full test suite
pytest tests/ -v

# Integration tests
pytest tests/integration/ -v

# Performance benchmark
python tests/storage/benchmark_repository.py

# Manual smoke test
# 1. Create session
# 2. Run command
# 3. Destroy session
```

**Commit:** `refactor(storage): remove legacy implementation and feature flags`

---

## Risk Mitigation

### Reduced Risk via Parallel Change

**Before (original plan):** Direct refactoring = high risk
**After (this plan):** Parallel implementations = medium risk

**Key safety mechanisms:**
1. **Characterization tests** - Capture current behavior before changes
2. **Contract tests** - Prove equivalence between implementations
3. **Feature flags** - Switch implementations without code changes
4. **Gradual rollout** - Test in production incrementally
5. **Easy rollback** - Just flip environment variable

### Rollback Strategy

**If new repository has issues:**
```bash
# Instant rollback (no code changes needed)
export LEON_USE_NEW_REPOSITORY=false

# Or per-entity rollback
export LEON_NEW_REPO_LEASES=false
```

**If critical bug found:**
1. Flip feature flag to legacy
2. Fix bug in new repository
3. Re-run contract tests
4. Flip back to new repository

### Testing Strategy

**Three layers of testing:**
1. **Characterization tests** - Document current behavior
2. **Contract tests** - Prove equivalence
3. **Integration tests** - Verify end-to-end behavior

**Test matrix:**
```
                Legacy Repo    New Repo
Characterization    ✓            -
Contract            ✓            ✓
Integration         ✓            ✓
```

---

## Success Criteria

- [ ] Characterization tests capture current behavior
- [ ] Repository protocol defined
- [ ] Legacy adapter wraps existing SQL
- [ ] New repository implemented
- [ ] Contract tests pass for both implementations
- [ ] All 7 files migrated to use repository interface
- [ ] Feature flag allows switching implementations
- [ ] All tests pass with new repository
- [ ] Legacy implementation removed
- [ ] No `import sqlite3` in sandbox layer
- [ ] No performance regressions
- [ ] Documentation updated

---

## Estimated Timeline

| Phase | Tasks | Time | Risk |
|-------|-------|------|------|
| Phase 0 | Characterization + abstraction | 2-3h | Low |
| Phase 1 | New repository implementation | 2-3h | Medium |
| Phase 2 | Parallel migration (7 files) | 3-4h | Medium |
| Phase 3 | Contract & cleanup | 2-3h | Low |
| **Total** | | **9-13h** | **Medium** |

**Note:** Slightly longer than original plan (6-9h → 9-13h), but MUCH safer.

---

## Comparison with Original Plan

| Aspect | Original Plan | This Plan |
|--------|---------------|-----------|
| **Risk** | High | Medium |
| **Rollback** | Code revert | Environment variable |
| **Testing** | Unit tests only | Characterization + Contract + Integration |
| **Migration** | Big bang per file | Gradual with feature flags |
| **Verification** | Manual | Automated contract tests |
| **Effort** | 6-9h | 9-13h |
| **Safety** | ⚠️ | ✅ |

**Trade-off:** 3-4 extra hours for dramatically reduced risk.

---

## Next Steps

1. **Create branch:** `refactor/storage-layer-separation`
2. **Phase 0:** Write characterization tests, extract schemas, create protocol
3. **Phase 0:** Implement legacy adapter, write contract tests
4. **Phase 1:** Implement new repository, verify contract tests pass
5. **Phase 2:** Migrate files one by one with feature flags
6. **Phase 3:** Remove legacy code, clean up flags
7. **PR:** Request review, merge to main

---

## Key Architectural Insights

1. **Abstraction before implementation** - Create interface first, not after
2. **Parallel change over big bang** - Run both implementations during migration
3. **Contract tests prove equivalence** - Not just "tests pass", but "same behavior"
4. **Feature flags enable safe rollout** - Production testing without risk
5. **Characterization tests preserve behavior** - Including quirks/bugs
6. **Explicit transactions** - Context managers, not implicit commits
7. **Dependency injection** - Easy to switch implementations

These patterns make refactoring **safe, incremental, and reversible**.
