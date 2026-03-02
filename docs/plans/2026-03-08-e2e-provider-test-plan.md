# E2E Provider Test — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Verify all 5 sandbox providers work end-to-end by uploading a file via API, asking the agent to read it, and confirming the agent response contains the file content.

**Architecture:** Sequential live API calls against a running backend. Each provider: setup gate → create thread → upload file → run agent → consume SSE → assert canary → cleanup. No pytest files — all executed via Bash in conversation.

**Tech Stack:** curl for REST calls, inline Python (via `uv run python -c`) for SSE consumption, jq for JSON parsing.

**Backend:** `http://127.0.0.1:8003` (worktree port from `git config --worktree`)

**Canary string:** `leon-e2e-canary-12345`

---

### Provider Reference

| Sandbox name | Provider type | Files dir in sandbox | Setup check |
|-------------|--------------|---------------------|-------------|
| `local` | local | N/A (host filesystem) | Always available |
| `docker` | docker | `/workspace/files/` | `docker info` exits 0 |
| `daytona_selfhost` | daytona | `/home/daytona/files/` | `curl -s http://localhost:3986` responds |
| `e2b` | e2b | `/home/user/workspace/files/` | `~/.leon/sandboxes/e2b.json` has api_key |
| `agentbay` | agentbay | `/home/wuying/files/` | `~/.leon/sandboxes/agentbay.json` has api_key |

---

### Task 0: Prerequisites

**Step 1: Verify backend is running on port 8003**

```bash
curl -sf http://127.0.0.1:8003/api/threads | jq '.threads | length'
```

Expected: a number (0 or more). If connection refused → start backend:

```bash
cd /Users/lexicalmathical/worktrees/leonai--orange-pr105-plus-workspace
env -u ALL_PROXY -u all_proxy uv run python -m backend.web.main &
```

**Step 2: Verify available sandbox providers**

```bash
curl -sf http://127.0.0.1:8003/api/settings/sandboxes | jq '[.types[] | {name, available}]'
```

Expected: list showing which providers loaded successfully. Providers with `available: false` will be skipped.

---

### Task 1: Test `local` provider

**Step 1: Create thread**

```bash
curl -sf -X POST http://127.0.0.1:8003/api/threads \
  -H 'Content-Type: application/json' \
  -d '{"sandbox": "local"}' | jq .
```

Expected: `{"thread_id": "<uuid>", "sandbox": "local", ...}`
Capture: `TID=<thread_id>`

**Step 2: Upload canary file**

```bash
curl -sf -X POST "http://127.0.0.1:8003/api/threads/${TID}/workspace/upload?path=test.txt" \
  -F "file=@-;filename=test.txt" <<< "leon-e2e-canary-12345" | jq .
```

Expected: `{"size_bytes": 21, ...}`

**Step 3: Start agent run**

```bash
curl -sf -X POST "http://127.0.0.1:8003/api/threads/${TID}/runs" \
  -H 'Content-Type: application/json' \
  -d '{"message": "Read the file test.txt that was uploaded to your files directory and tell me its exact content. Just show me the content."}' | jq .
```

Expected: `{"run_id": "<uuid>", "thread_id": "..."}`
Capture: `RUN_ID=<run_id>`

**Step 4: Consume SSE until run_done, extract agent response**

```bash
uv run python -c "
import httpx, json, sys

base = 'http://127.0.0.1:8003'
tid = '${TID}'
full_text = ''
events = []

with httpx.stream('GET', f'{base}/api/threads/{tid}/events?after=0', timeout=120) as r:
    event_type = ''
    for line in r.iter_lines():
        if line.startswith('event:'):
            event_type = line[6:].strip()
        elif line.startswith('data:'):
            try:
                data = json.loads(line[5:])
            except json.JSONDecodeError:
                continue
            if event_type == 'text' and 'content' in data:
                full_text += data['content']
            if event_type in ('tool_call', 'tool_result'):
                name = data.get('name', '')
                print(f'  [{event_type}] {name}', file=sys.stderr)
            if event_type == 'run_done':
                print(f'  [run_done]', file=sys.stderr)
                break

canary = 'leon-e2e-canary-12345'
passed = canary in full_text
print(f'\\n--- Agent response (truncated) ---')
print(full_text[:500])
print(f'\\n--- RESULT: {\"PASS\" if passed else \"FAIL\"} ---')
sys.exit(0 if passed else 1)
"
```

Expected: `PASS` — agent response contains the canary string.

**Step 5: Cleanup**

```bash
curl -sf -X DELETE "http://127.0.0.1:8003/api/threads/${TID}" | jq .
```

---

### Task 2: Test `docker` provider

**Step 1: Setup check**

```bash
docker info > /dev/null 2>&1 && echo "READY" || echo "SKIP: docker not available"
```

If SKIP → move to Task 3.

**Step 2–5: Same flow as Task 1** with these substitutions:

- Create thread: `{"sandbox": "docker"}`
- Agent prompt: `"Read the file test.txt in /workspace/files/ and tell me its exact content. Just show me the content."`
- Timeout: 120s (container startup adds latency)

---

### Task 3: Test `daytona_selfhost` provider

**Step 1: Setup check**

```bash
curl -sf http://localhost:3986 > /dev/null 2>&1 && echo "READY" || echo "SKIP: daytona tunnel not open"
```

If SKIP → move to Task 4. To fix: run `~/Codebase/leonai/ops/tunnel.sh`.

**Step 2–5: Same flow as Task 1** with these substitutions:

- Create thread: `{"sandbox": "daytona_selfhost"}`
- Agent prompt: `"Read the file test.txt in /home/daytona/files/ and tell me its exact content. Just show me the content."`
- Timeout: 120s (remote sandbox boot)

---

### Task 4: Test `e2b` provider

**Step 1: Setup check**

```bash
python3 -c "import json; c=json.load(open('$HOME/.leon/sandboxes/e2b.json')); print('READY' if c.get('e2b',{}).get('api_key') else 'SKIP: no api_key')"
```

If SKIP → move to Task 5.

**Step 2–5: Same flow as Task 1** with these substitutions:

- Create thread: `{"sandbox": "e2b"}`
- Agent prompt: `"Read the file test.txt in /home/user/workspace/files/ and tell me its exact content. Just show me the content."`
- Timeout: 120s

---

### Task 5: Test `agentbay` provider

**Step 1: Setup check**

```bash
python3 -c "import json; c=json.load(open('$HOME/.leon/sandboxes/agentbay.json')); print('READY' if c.get('agentbay',{}).get('api_key') else 'SKIP: no api_key')"
```

If SKIP → done.

**Step 2–5: Same flow as Task 1** with these substitutions:

- Create thread: `{"sandbox": "agentbay"}`
- Agent prompt: `"Read the file test.txt in /home/wuying/files/ and tell me its exact content. Just show me the content."`
- Timeout: 120s

---

### Task 6: Summary

Print a results table:

```
| Provider          | Result |
|-------------------|--------|
| local             | PASS/FAIL/SKIP |
| docker            | PASS/FAIL/SKIP |
| daytona_selfhost  | PASS/FAIL/SKIP |
| e2b               | PASS/FAIL/SKIP |
| agentbay          | PASS/FAIL/SKIP |
```

---

## Extending This Plan

The flow above is the **minimal core**. Additional steps per provider:

- **Write via tool:** Ask agent to create a file, then verify it exists on disk / via API
- **Shell command:** Ask agent to run `uname -a` or `python3 --version`, verify output
- **Pause/resume:** `POST .../sandbox/pause` → `POST .../sandbox/resume` → verify agent still works
- **Workspace sync:** Upload after session exists, verify file appears in sandbox
- **Multi-file:** Upload directory structure, ask agent to `ls -la`, verify listing
- **Error paths:** Wrong sandbox name, upload to nonexistent thread, oversized file

Each extension follows the same pattern: API call → agent action → verify output.
