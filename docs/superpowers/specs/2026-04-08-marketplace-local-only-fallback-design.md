# Marketplace Local-Only Publish Fallback

## Goal

Decide and isolate the remaining local-only publish fallback in `backend/web/services/marketplace_client.py` without touching marketplace lineage or the repo-backed web publish contract.

## Current Facts

- `backend/web/routers/marketplace.py` always calls `marketplace_client.publish()` with `user_repo + agent_config_repo`
- in current code, `marketplace_client.publish()` still has an `else` branch that:
  - reads `members_dir() / user_id`
  - serializes bundle files through `_serialize_user_snapshot()`
  - loads the bundle through `AgentLoader().load_bundle(member_dir)`
- this branch is not part of the normal web publish path

## In Scope

- the local-only `publish()` fallback branch
- whether it should remain as an explicit path or fail loudly
- proof that the web publish contract is unaffected

## Out Of Scope

- repo-backed publish path
- marketplace lineage / `meta.json.source`
- download / upgrade / install
- outward API payloads
- `member_service.delete_member()`

## Recommended Cut

Fail loudly for `publish()` calls that do not provide `user_repo + agent_config_repo`.

Reason:

- the live web route already proves repos are the normal contract
- leaving the fallback inside the same entrypoint keeps an orphan filesystem publish shell alive
- no in-repo caller currently needs the fallback

If a true local/CLI publish path is needed later, it should get its own explicit entrypoint instead of hiding behind the shared web service function.

## Target Contract

1. `marketplace_client.publish()` is repo-rooted for the normal web/API path.
2. Calls without `user_repo + agent_config_repo` fail loudly instead of silently reading local member bundles.
3. No lineage fields are redesigned in the same cut.
4. Download/upgrade/install remain untouched.

## Proof Hints

- caller proof: `rg` shows only router/tests use `marketplace_client.publish()`
- red test candidate: `publish()` without repos raises a clear `RuntimeError`
- regression proof: current repo-backed publish tests stay green

## Stopline

Do not:

- redesign `meta.json.source`
- reopen the repo-backed publish island already superseded on `#259`
- touch `member_service.delete_member()`
