# Leon AI Troubleshooting Guide

## Sandbox Issues

### PTY Creation Failures

**Error:** `fork/exec /usr/bin/bash: no such file or directory`

**Cause:** Workspace image or runner container missing bash at `/usr/bin/bash`

**Solution:**
1. Verify bash in workspace: `docker exec <workspace_id> ls -la /usr/bin/bash`
2. Verify bash in runner: `docker exec daytona-runner-1 ls -la /usr/bin/bash`
3. If missing, rebuild image with bash installed

**For Daytona self-hosted:**
```dockerfile
FROM your-base-image
RUN apt-get update && apt-get install -y bash
RUN ln -s /bin/bash /usr/bin/bash
```

---

**Error:** `PTY session already exists`

**Cause:** Previous PTY creation failed but left session registered

**Solution:** Restart sandbox session. Leon includes automatic cleanup (as of 2026-03-10).

---

### Timeout Errors

**Error:** `Failed to create sandbox within 60s`

**Cause:** Network isolation - runner can't reach workspace containers

**Solution:**
1. Check runner networks: `docker network inspect bridge`
2. Connect runner to bridge: `docker network connect bridge daytona-runner-1`
3. Restart runner

---

### Docker Provider Issues

**Error:** Docker CLI hangs or times out

**Cause:** Proxy environment variables inherited by Docker CLI

**Solution:** Leon automatically strips `http_proxy`/`https_proxy`. If issues persist:
1. Check `docker_host` in config
2. Verify Docker daemon is running: `docker ps`
3. Test Docker directly: `docker run hello-world`

---

## Configuration Issues

### Invalid Config Fields

**Error:** Config fields silently ignored

**Cause:** Pydantic schema doesn't define the field

**Solution:** Use `validate_sandbox_config()` to check for warnings:
```python
from sandbox.config import SandboxConfig, validate_sandbox_config

config = SandboxConfig.load("daytona_selfhost")
warnings = validate_sandbox_config(config)
for w in warnings:
    print(f"Warning: {w}")
```

---

### Missing API Keys

**Error:** `API key required but not found`

**Cause:** Environment variable not set

**Solution:**
1. Create `~/.leon/config.env`:
   ```bash
   E2B_API_KEY=your_key
   DAYTONA_API_KEY=your_key
   AGENTBAY_API_KEY=your_key
   ```
2. Restart Leon to pick up changes

---

### Environment Variables Not Loaded

**Error:** Config uses `${VAR_NAME}` but variable not found

**Cause:** Environment not loaded before Leon starts

**Solution:**
1. Export variables in shell: `export E2B_API_KEY=...`
2. Or use absolute values in config (not recommended for secrets)

---

## Performance Issues

### Slow Command Execution

**Cause:** Network latency to cloud sandbox providers

**Solution:**
1. Use local Docker for development
2. Choose provider region closest to you
3. Check network connectivity: `ping app.daytona.io`

---

### Memory Limits

**Error:** Sandbox runs out of memory

**Solution:**
1. Check provider limits (varies by provider)
2. For Docker: increase container memory limit
3. Monitor usage: `leonai sandbox metrics <id>`

---

### Disk Space

**Error:** No space left on device

**Solution:**
1. Clean up old sessions: `leonai sandbox destroy-all-sessions`
2. For Docker: `docker system prune`
3. Check disk usage: `df -h`

---

## Debug Mode

### Enable Debug Logging

**Backend:**
```bash
export LEON_LOG_LEVEL=DEBUG
uvicorn main:app --log-level debug
```

**Sandbox operations:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

### Log Locations

- **Backend logs:** stdout/stderr from uvicorn
- **Database (main):** `~/.leon/leon.db`
- **Database (sandbox):** `~/.leon/sandbox.db`
- **Config:** `~/.leon/config.json`, `~/.leon/config.env`
- **Sandbox configs:** `~/.leon/sandboxes/*.json`

---

### Common Log Patterns

**PTY creation:**
```
[DaytonaProvider] PTY creation failed: ...
```

**Network issues:**
```
Failed to connect to ...
Connection timeout ...
```

**Config issues:**
```
Config validation warning: ...
```

---

## LLM Provider Issues

### API Key Not Found

**Error:** `OPENAI_API_KEY not set` or model requests return 401

**Cause:** API key not configured or not loaded into environment

**Solution:**
1. Run `leonai config` to set `OPENAI_API_KEY` and `OPENAI_BASE_URL` interactively
2. Or edit `~/.leon/config.env` directly:
   ```
   OPENAI_API_KEY=sk-...
   OPENAI_BASE_URL=https://api.openai.com/v1
   MODEL_NAME=gpt-4o
   ```
3. Keys in `config.env` are loaded automatically on startup. Environment variables already set in the shell take precedence.

**Note:** `OPENAI_BASE_URL` must end with `/v1`. Leon auto-appends it if missing (e.g. `https://yunwu.ai` becomes `https://yunwu.ai/v1`).

---

### Rate Limits / 429 Errors

**Error:** `Rate limit exceeded` or HTTP 429

**Cause:** Too many requests to the LLM provider

**Solution:**
1. Wait and retry (Leon does not auto-retry on 429)
2. Switch to a provider with higher rate limits
3. If using a proxy (e.g. OpenRouter), check your plan's RPM/TPM limits

---

### Model Not Found / 404

**Error:** `Model not found` or HTTP 404

**Cause:** The model name in config does not exist at the provider

**Solution:**
1. Check `MODEL_NAME` in `~/.leon/config.env`
2. Verify the model exists at your `OPENAI_BASE_URL` endpoint
3. Some providers require specific model name formats (e.g. `openrouter/model-name`)

---

### SOCKS Proxy Error

**Error:** `socksio` related errors from LLM client

**Cause:** `all_proxy=socks5://...` inherited from shell. The LLM client picks up `all_proxy` even when `https_proxy` is already set.

**Solution:** Unset proxy vars when starting:
```bash
env -u ALL_PROXY -u all_proxy leonai
```

For the web backend:
```bash
env -u ALL_PROXY -u all_proxy uv run python -m backend.web.main
```

---

## Web UI Issues

### Backend Not Starting

**Error:** Backend fails to start or uvicorn exits immediately

**Solution:**
1. Check if the port is already in use: `lsof -i :<port>`
2. Kill zombie processes: `kill -9 <PID>`
3. Start with explicit env: `env -u ALL_PROXY -u all_proxy uv run python -m backend.web.main`
4. Check logs for import errors — missing dependencies may need `uv sync`

---

### Port Conflicts (Worktrees)

**Error:** Backend starts but frontend can't reach it, or requests go to wrong backend

**Cause:** In a git worktree, the frontend proxies to a port defined in git config. If the backend runs on a different port, requests are lost.

**Solution:**
1. Check the expected port: `git config --worktree --list | grep port`
2. Start the backend on that port
3. Use `lsof -i :<port>` to find zombie processes that survived `pkill`

---

### Frontend Build Errors

**Error:** Frontend build fails or shows blank page

**Solution:**
1. Clear node_modules and reinstall: `cd frontend && rm -rf node_modules && npm install`
2. Check Node.js version (recommended: 18+)
3. For blank page, check browser console for JS errors

---

## Multi-Agent Chat Issues

### Thread/Entity Confusion

**Error:** Agent replies appear in wrong conversation or agent identity is mixed up

**Cause:** Thread IDs map 1:1 to agent instances. Mixing up thread IDs causes cross-talk.

**Solution:**
1. Each agent conversation must use a unique thread ID
2. When resuming, use `--thread <id>` or `-c` to continue the correct conversation
3. Check `~/.leon/leon.db` table `conversations` for thread mapping

---

### Agent Not Responding

**Error:** Agent appears to receive message but produces no output

**Cause:** Sandbox session may be paused or destroyed, or the LLM call is timing out

**Solution:**
1. Check sandbox state: `leonai sandbox ls`
2. If session is paused, resume it: `leonai sandbox resume <id>`
3. Check LLM provider connectivity (see LLM Provider Issues above)
4. Enable debug logging: `export LEON_LOG_LEVEL=DEBUG`

---

### Member/Entity Not Found

**Error:** `Member not found` or `Entity not found` when starting a chat

**Cause:** The member definition or entity record is missing from the database

**Solution:**
1. Verify members exist in `~/.leon/members/` directory
2. Check the database: entities are stored in `~/.leon/leon.db`
3. Recreate the member if its definition file was deleted

---

## Reporting Issues

When reporting issues, include:

1. **Leon version:** `leonai --version`
2. **Provider:** Which sandbox provider (docker, e2b, daytona, etc.)
3. **Error message:** Full error text from logs
4. **Steps to reproduce:** Minimal example that triggers the issue
5. **Environment:** OS, Python version, Docker version (if applicable)

**Example:**
```
Leon version: 0.3.0
Provider: daytona_selfhost
Error: fork/exec /usr/bin/bash: no such file or directory
Steps: 1. Start Leon with --sandbox daytona_selfhost
       2. Send any command
       3. Error occurs
Environment: macOS 14.0, Python 3.12, Docker 24.0
```

---

## See Also

- [Deployment Guide](./deployment/DEPLOYMENT.md) - Setup instructions
- [Sandbox Documentation](./sandbox/SANDBOX.md) - Provider details
- [GitHub Issues](https://github.com/yourusername/leonai/issues) - Report bugs
