# Database Refactor Dev Replay 26: Outward Sandbox Template Contract Cleanup Preflight

## Goal

Define the first implementation slice that renames the outward
owner-facing/frontend-facing `recipe` contract toward `sandbox template`
language without yet changing the underlying library resource taxonomy.

This checkpoint is preflight only. It does not implement the rename yet.

## Why This Comes Next

Replay-25 already classified the current `recipe` residue into three buckets:

- outward contract residue
- taxonomy/internal residue
- protected truths

That means replay-26 should stop debating scope and instead define the first
actual rename slice.

The correct first slice is **not** a full `recipe` eradication pass. It is the
outward contract cleanup:

- user-visible naming
- owner-facing request/response naming
- frontend API/types/page naming

While explicitly leaving the deeper library taxonomy alone for one more lane.

## Current Code Facts

### 1. Backend request models still expose outward `recipe` fields

`backend/web/models/requests.py` still defines:

- `CreateThreadRequest.recipe_id`
- `SaveThreadLaunchConfigRequest.recipe_id`

Those are owner-facing contract fields, not storage internals.

### 2. Frontend API/types still expose outward `recipe` naming

`frontend/app/src/api/client.ts` still uses:

- `CreateThreadOptions.recipeId`
- `createThread(...)` writing `recipe_id`
- default-config save/load flows carrying `recipe_id`

`frontend/app/src/api/types.ts` still defines:

- `RecipeSnapshot`
- `ThreadLaunchConfig.recipe_id`
- `ThreadLaunchConfig.recipe`

These are the clearest outward rename targets.

### 3. Page-level orchestration is still recipe-shaped

`frontend/app/src/pages/NewChatPage.tsx` still uses:

- `selectedRecipeId`
- `recipeOptions`
- `selectedRecipeSnapshot`
- save/create payloads built from `recipe_id` and `recipe`

This means the outward rename is not finished unless page-state naming also
moves.

### 4. Library taxonomy is still recipe-shaped and intentionally out of lane

Examples that must stay out of replay-26:

- `list_library("recipe", ...)`
- `create_resource("recipe", ...)`
- `LibraryType = "skill" | "mcp" | "agent" | "recipe"`
- `libraryRecipes`
- `/library/recipe/:id`

These belong to the later taxonomy lane, not the first outward contract lane.

## Chosen Direction

Replay-26 should rename the outward contract to sandbox-template language while
keeping the internal library taxonomy temporarily stable.

The intended end state after replay-26 is:

- owner-facing/backend request fields say `sandbox_template_*`
- frontend API/types/page state say `sandbox template`
- internal library resource taxonomy may still say `"recipe"`

This is an intentionally split state, but it is an honest one:

- the product-facing concept becomes truthful first
- taxonomy/internal cleanup comes later as a separate checkpoint

## Exact Target Naming

Replay-26 should bias toward the following outward naming:

- `recipe_id` -> `sandbox_template_id`
- `recipe` -> `sandbox_template`
- `RecipeSnapshot` -> `SandboxTemplateSnapshot`
- `recipeId` -> `sandboxTemplateId`
- `selectedRecipeId` -> `selectedSandboxTemplateId`
- `recipeOptions` -> `sandboxTemplateOptions`

The rename should stay at the outward contract and page/component state layer.

## Exact Write Set

### Authorized backend code

- `backend/web/models/requests.py`
- `backend/web/routers/threads.py`

`threads.py` is in-lane only for synchronized request/response payload handling
that must move with the request model rename.

### Authorized frontend code

- `frontend/app/src/api/client.ts`
- `frontend/app/src/api/types.ts`
- `frontend/app/src/pages/NewChatPage.tsx`

### Allowed if focused RED proves clearly necessary

- `frontend/app/src/pages/NewChatPage.test.tsx`
- `frontend/app/src/api/client.test.ts`
- `tests/Integration/test_thread_launch_config_contract.py`
- `tests/Integration/test_threads_router.py`

### Explicitly out of lane

- `backend/web/services/library_service.py`
- `frontend/app/src/store/app-store.ts`
- `frontend/app/src/pages/MarketplacePage.tsx`
- `frontend/app/src/pages/LibraryItemDetailPage.tsx`
- `frontend/app/src/components/RecipeEditor.tsx`
- any repo/storage contract or runtime provider code

## Planned Mechanism

Replay-26 should be a synchronized outward rename, not a long-lived bilingual
bridge.

### Backend request side

Rename outward request fields:

- `CreateThreadRequest.recipe_id` -> `sandbox_template_id`
- `SaveThreadLaunchConfigRequest.recipe_id` -> `sandbox_template_id`

Route handling should consume the new outward fields while continuing to call
internal helpers/library layers however they currently need to be called.

### Frontend API/types side

Rename outward API contract terms:

- `CreateThreadOptions.recipeId` -> `CreateThreadOptions.sandboxTemplateId`
- `ThreadLaunchConfig.recipe_id` -> `ThreadLaunchConfig.sandbox_template_id`
- `ThreadLaunchConfig.recipe` -> `ThreadLaunchConfig.sandbox_template`
- `RecipeSnapshot` -> `SandboxTemplateSnapshot`

Serializer/parser behavior should follow those new names at the outward
boundary.

### Page orchestration side

Rename local state and view-model terms in `NewChatPage.tsx` so the page no
longer speaks `recipe` as the product concept.

The page may still source its options from `libraryRecipes` for now. Replay-26
is not required to rename store taxonomy.

## No Long-Lived Alias Rule

Replay-26 should avoid a permanent dual outward contract such as:

- request accepts both `recipe_id` and `sandbox_template_id`
- response emits both `recipe` and `sandbox_template`
- frontend parser accepts both forever

If one short internal bridge is temporarily required inside the same slice, it
must be:

- internal only
- tightly scoped
- removed before claiming replay-26 done

The target state is one outward name, not two.

## Test Plan

Replay-26 should be driven by focused contract proof.

Required proof:

1. backend request models and route tests accept the new outward
   `sandbox_template_*` fields
2. thread-create new-mode path still resolves the selected template correctly
3. default-config save/load paths serialize and parse `sandbox_template_id` and
   `sandbox_template`
4. frontend API client serializes/parses the new names correctly
5. `NewChatPage` still constructs the same create/save behavior while using the
   new outward naming

Not required:

- library taxonomy rename
- runtime/provider proof
- schema/migration proof
- marketplace/library-page rename
- Playwright YATU

## Stopline

Replay-26 must not:

- rename the `"recipe"` library resource type
- rename `libraryRecipes`
- rename `/library/recipe/:id`
- rewrite library CRUD dispatch
- change storage/repo schema or contracts
- change runtime/provider payload truth
- change `lease_id` runtime/resource surfaces
- widen into marketplace/library taxonomy cleanup

## Expected Artifact

If replay-26 lands cleanly, the result should be easy to state:

- the outward product/API contract now says `sandbox template`
- the internal library taxonomy may still say `recipe`
- there is no permanent bilingual outward contract left behind

## Open Question For Ruling

Is replay-26 the right first implementation lane to rename the outward
owner-facing/frontend-facing `recipe` contract to `sandbox template` language
without yet renaming the underlying library resource taxonomy?
