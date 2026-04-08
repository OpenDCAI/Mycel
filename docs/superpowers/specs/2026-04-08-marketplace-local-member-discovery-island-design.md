# Marketplace Local Member Discovery Island

## Goal

Isolate the remaining local member-bundle discovery shell in `backend/web/services/marketplace_client.py` so the web publish path is repo-rooted only.

## Current Facts

- `backend/web/routers/marketplace.py` always passes `user_repo` and `agent_config_repo` into `marketplace_client.publish()`
- `marketplace_client.publish()` still contains a fallback branch that reads from `members_dir() / user_id`
- that fallback serializes a local member bundle through `_serialize_user_snapshot()` and `AgentLoader().load_bundle(member_dir)`
- the fallback is not needed for the normal web router path

## In Scope

- `marketplace_client.publish()` path selection for member publish
- explicit separation of repo-rooted publish vs local legacy bundle publish
- tests proving the web path stays repo-rooted and does not rely on local member bundles

## Out Of Scope

- marketplace lineage root replacement
- `meta.json.source` redesign
- download/upgrade/install flows
- outward marketplace payload shape
- router auth or ownership checks

## Target Contract

1. Web member publish is repo-rooted.
2. Local member-dir bundle discovery is not part of the normal web publish path.
3. If a caller wants the old local-bundle behavior, it must be explicit instead of silently sharing the live web entrypoint.
4. No new backward-compat fallback is added.

## Candidate Cut

Recommended narrow seam:

- keep a repo-rooted `publish()` path for web callers
- move the local filesystem serialization path behind an explicit helper or fail-loud branch
- do not touch the `meta.json.source` lineage merge in the same cut

## Proof Hints

- caller proof: router already passes repos
- behavior proof: repo-backed publish tests stay green
- red test candidate: member publish without repos should no longer silently behave like the web live path

## Stopline

Do not:

- rewrite marketplace lineage
- change install/download flows
- change outward API payloads
- mix this seam with `member_service`
