# E2E Provider Test Design

## Goal

Verify all 5 sandbox providers (local, docker, daytona, e2b, agentbay) work end-to-end via live backend API calls. The test proves the full chain: thread creation → file upload → agent reads file → correct response.

## Approach

Sequential per-provider. Each provider runs through the same minimal flow. Providers that fail setup checks are skipped, not blocked.

## Test Flow (per provider)

```
Setup Check → Create Thread → Upload File → Send Message → Consume SSE → Assert → Cleanup
```

| Step | API | Success |
|------|-----|---------|
| Setup Check | Provider-specific (see below) | Gate passes |
| Create Thread | `POST /api/threads {"sandbox": "<provider>"}` | 200, thread_id |
| Upload File | `POST /api/threads/{id}/workspace/upload` with `test.txt` = `leon-e2e-canary-12345` | 200, size > 0 |
| Send Message | `POST /api/threads/{id}/runs {"message": "Read test.txt in /workspace/files/ and tell me its content"}` | 200, run_id |
| Consume SSE | `GET /api/threads/{id}/events?after=0` until `run_done` | run_done within 120s |
| Assert | Concatenated `text` events contain `leon-e2e-canary-12345` | Canary found |
| Cleanup | `DELETE /api/threads/{id}` | 200 |

## Provider Order & Setup Checks

| # | Provider | Check | How |
|---|----------|-------|-----|
| 1 | local | Always available | None |
| 2 | docker | Docker daemon | `docker info` exits 0 |
| 3 | daytona | Tunnel + config | `curl localhost:3986/health` + `daytona_selfhost.json` |
| 4 | e2b | API key | `e2b.json` + key present |
| 5 | agentbay | API key | `agentbay.json` + key present |

## SSE Consumption

Use httpx streaming to read the event stream. Accumulate `text` event content into a string. Break on `run_done`. Timeout 120s.

Show raw SSE events as they arrive — this is the real agent trace.

## Pass/Fail

- Canary string in response = **PASS**
- Timeout or canary missing = **FAIL**
- Setup check fails = **SKIP**

## Extensibility

This is the minimal flow. Additional steps per provider can be added later:
- Write file via agent tool, verify on disk
- Run shell command in sandbox
- Pause/resume sandbox mid-conversation
- Workspace sync verification (upload before session, verify in sandbox)
- Multi-file upload and directory listing
