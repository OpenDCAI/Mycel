# Workspace Sync Master Plan

**Goal:** Complete workspace synchronization system with proper abstraction, optimization, and comprehensive testing across all sandbox types.

**Status:** Planning Complete | Implementation Pending

---

## Plan Tree

```
workspace-sync-master-plan/
├── Phase 1: E2E Fix (PRIORITY)
│   └── 2026-03-07-workspace-sync-e2e-fix.md
│       ├── Task 1: Create E2E Test Framework
│       ├── Task 2: Fix Local Sandbox
│       ├── Task 3: Fix Daytona Sandbox
│       ├── Task 4: Fix Self-Host Daytona
│       ├── Task 5: Fix E2B Sandbox
│       ├── Task 6: Verify Docker Sandbox
│       └── Task 7: Run All Tests
│
└── Phase 2: Sync Manager (OPTIMIZATION)
    └── 2026-03-07-workspace-sync-manager.md
        ├── Task 1: Design SyncManager Architecture
        ├── Task 2: Implement State Tracking
        ├── Task 3: Implement Change Detection
        ├── Task 4: Implement Full Sync Strategy
        ├── Task 5: Implement Incremental Sync Strategy
        ├── Task 6: Implement Strategy Selection
        ├── Task 7: Integrate with Existing Code
        ├── Task 8: Add Error Handling
        └── Task 9: End-to-End Testing
```

**Execution Order:** Phase 1 → Phase 2

**Rationale:** Fix immediate issues first (E2E), then optimize architecture (Sync Manager)

---

## Implementation Workflow

### Phase 1: E2E Fix (Days 1-2)

**Objective:** Get all sandbox types working with file upload

**Steps:**
1. Create E2E test framework (1 hour)
2. Fix local sandbox workspace config (2 hours)
3. Fix Daytona/self-host/E2B sync (3 hours)
4. Verify Docker still works (30 min)
5. Run full test suite (30 min)

**Success Criteria:**
- All 5 sandbox types pass E2E tests
- Agent can read uploaded files in all environments
- No regression in existing functionality

### Phase 2: Sync Manager (Days 3-5)

**Objective:** Replace ad-hoc sync with proper abstraction

**Steps:**
1. Design architecture (1 hour)
2. Implement state tracking with Leon's DB abstraction (2 hours)
3. Implement change detection (2 hours)
4. Implement sync strategies (4 hours)
5. Integrate with existing code (3 hours)
6. Add error handling (2 hours)
7. Add comprehensive tests (2 hours)

**Success Criteria:**
- Only changed files are synced (not full workspace)
- State tracking uses Leon's SQLite kernel
- All tests pass
- No abstraction leaks

---

## Quality Gates

### Per-Task Quality Gates

**Before marking task complete:**
1. ✅ Test written and passes
2. ✅ Code follows Leon conventions (no raw SQLite, use abstractions)
3. ✅ No abstraction leaks (check imports, dependencies)
4. ✅ Committed to git with clear message
5. ✅ No linting errors

**Verification Commands:**
```bash
# Run specific test
pytest tests/path/to/test.py::test_name -v -s

# Check for abstraction leaks
grep -r "import sqlite3" sandbox/sync/  # Should only be in kernel.py

# Run linter
ruff check .
```

### Per-Phase Quality Gates

**Phase 1 Complete When:**
- All E2E tests pass: `pytest tests/e2e/ -v`
- Manual verification done for all 5 sandbox types
- No regression in existing functionality
- All changes committed

**Phase 2 Complete When:**
- All sync manager tests pass: `pytest tests/sandbox/sync/ -v`
- E2E tests still pass: `pytest tests/e2e/ -v`
- Performance improved (fewer file uploads)
- Old `workspace_sync.py` removed
- All changes committed

---

## Unit Implementation Rules

### Code Quality Standards

**MUST:**
- Use Leon's database abstraction (`connect_sqlite_role(SQLiteDBRole.SANDBOX)`)
- Use type hints for all function signatures
- Add docstrings for public methods
- Follow existing code patterns in Leon
- Use `@@@comment` format for tricky parts
- Fail loudly (no silent fallbacks)

**MUST NOT:**
- Use raw `sqlite3.connect()` directly
- Add defensive edge case handling (keep simple)
- Use monkeypatch, nested functions, globals
- Swallow exceptions without logging
- Add features not in the plan (YAGNI)

### Test-Driven Development

**Every task follows TDD:**
1. Write test first
2. Run test → verify FAIL
3. Write minimal implementation
4. Run test → verify PASS
5. Commit

**Test Naming:**
- `test_<component>_<behavior>` (e.g., `test_sync_state_track_file`)
- One assertion per test when possible
- Use descriptive variable names

---

## Manual Test Procedures

### Backend API-Based Testing

**Test each sandbox type with this flow:**

```python
# 1. Create thread
response = httpx.post("http://127.0.0.1:8003/api/threads",
                      json={"sandbox": "docker"})
thread_id = response.json()["thread_id"]

# 2. Upload file
files = {"file": ("test.txt", b"Test content")}
response = httpx.post(f"http://127.0.0.1:8003/api/threads/{thread_id}/workspace/upload",
                      files=files)
assert response.status_code == 200

# 3. Send message
response = httpx.post(f"http://127.0.0.1:8003/api/threads/{thread_id}/messages",
                      json={"message": "Read /workspace/files/test.txt"})
assert response.status_code == 200

# 4. Wait for response
time.sleep(5)

# 5. Get messages
response = httpx.get(f"http://127.0.0.1:8003/api/threads/{thread_id}")
messages = response.json()["messages"]
agent_response = messages[-1]["content"]

# 6. Verify
assert "Test content" in agent_response
```

**Run for each sandbox type:**
- `local`
- `docker`
- `daytona`
- `daytona_selfhost`
- `e2b`

---

## End-to-End Testing Strategy

### Automated E2E Tests

**Location:** `tests/e2e/`

**Test Pattern:**
```python
def test_<sandbox>_sandbox_file_access(api_client, test_file_content):
    thread_id = create_thread(api_client, "<sandbox>")
    upload_file(api_client, thread_id, "test.txt", test_file_content)
    send_message(api_client, thread_id, "Read /workspace/files/test.txt")
    time.sleep(5)
    messages = get_thread_messages(api_client, thread_id)
    assert "Test file content" in messages[-1]["content"]
```

**Coverage:**
- ✅ File upload via API
- ✅ Agent receives upload notification
- ✅ Agent can access uploaded file
- ✅ File content is correct
- ✅ Works across all sandbox types

### Regression Testing

**After each phase:**
```bash
# Run all tests
pytest tests/ -v

# Run only E2E tests
pytest tests/e2e/ -v

# Run only sync manager tests
pytest tests/sandbox/sync/ -v
```

**Expected:** All tests pass, no regressions

---

## Summary

**This master plan coordinates two sub-plans:**

1. **E2E Fix Plan** (Priority): Fix immediate file upload issues across all sandbox types
2. **Sync Manager Plan** (Optimization): Replace ad-hoc sync with proper abstraction

**Key Principles:**
- Test-driven development (write test → fail → implement → pass)
- Use Leon's abstractions (no raw SQLite, no abstraction leaks)
- Fail loudly (no silent fallbacks)
- YAGNI (only implement what's in the plan)
- Quality gates at every level (task, phase, project)

**Execution:**
1. Start with Phase 1 (E2E Fix)
2. Verify all sandbox types work
3. Move to Phase 2 (Sync Manager)
4. Verify optimization works without breaking E2E

**Success Metrics:**
- All 5 sandbox types pass E2E tests
- Only changed files are synced (not full workspace)
- No abstraction leaks in codebase
- All tests pass
