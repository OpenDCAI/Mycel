# Database Refactor Dev Replay 25: Recipe To Sandbox Template Inventory Preflight

## Goal

Classify the remaining `recipe` naming surface into clear layers before any
rename lane starts.

This checkpoint is doc/ruling only. It does not rename resource types, request
fields, frontend routes, library APIs, storage contracts, runtime/provider
behavior, SQL/migrations, or live DB state.

## Why This Comes Next

Replay-22 through replay-24 finished the launch-config shell cleanup around
existing sandbox selection:

- outward shell now says `existing_sandbox_id`
- backend helper truth now also says `existing_sandbox_id`
- runtime/resource surfaces still honestly keep `lease_id`

That means the biggest remaining naming residue is no longer about existing
sandbox selection. It is the older `recipe` term itself.

Right now `recipe` simultaneously means:

- the user-facing sandbox template concept
- an owner-facing request/response contract field
- a library resource type
- a backend/storage internal identifier family

Those are not one layer. Replay-25 exists to separate them before we rename
anything.

## Current Code Facts

### 1. Owner-facing launch-config and thread-create contract still says `recipe`

Examples:

- `backend/web/models/requests.py`
  - `CreateThreadRequest.recipe_id`
  - `SaveThreadLaunchConfigRequest.recipe_id`
- `backend/web/services/thread_launch_config_service.py`
  - `recipe_id`
  - `recipe`
- `backend/web/routers/threads.py`
  - `_resolve_owned_recipe_snapshot(...)`
  - thread create path still resolves `payload.recipe_id`

This is not just UI wording. It is part of the owner-facing backend contract.

### 2. Frontend API/types/UI still model sandbox templates through `recipe`

Examples:

- `frontend/app/src/api/types.ts`
  - `RecipeSnapshot`
  - `ThreadLaunchConfig.recipe_id`
  - `UserLeaseSummary.recipe_id`
  - `UserLeaseSummary.recipe_name`
- `frontend/app/src/api/client.ts`
  - `CreateThreadOptions.recipeId`
  - `createThread(...)` sending `recipe_id`
- `frontend/app/src/pages/NewChatPage.tsx`
  - `selectedRecipeId`
  - `recipeOptions`
  - `"选择沙盒模板"` UI built from `recipe`-shaped state
- `frontend/app/src/components/RecipeEditor.tsx`

This means the frontend still treats the user-visible sandbox template concept
as `recipe` in both code and API contract.

### 3. Library/store/router also still promote `recipe` as a first-class resource type

Examples:

- `backend/web/services/library_service.py`
  - `list_library("recipe", ...)`
  - `create_resource("recipe", ...)`
  - `update/delete` paths keyed on `"recipe"`
- `frontend/app/src/store/app-store.ts`
  - `LibraryType = "skill" | "mcp" | "agent" | "recipe"`
  - `libraryRecipes`
- `frontend/app/src/pages/MarketplacePage.tsx`
  - installed sub-tab `"recipe"`
  - `/library/recipe/:id`
- `frontend/app/src/pages/LibraryItemDetailPage.tsx`
  - `DetailLibraryType = "skill" | "agent" | "recipe"`

This is deeper than a local variable rename. `recipe` is currently a resource
taxonomy decision.

### 4. The target term already exists elsewhere as `sandbox template`

There is already evidence that the repo is moving toward the new concept:

- `backend/web/services/thread_runtime_binding_service.py`
  - `sandbox_template_id`
- UI wording already says `"Sandbox"` / `"沙盒模板"` in several places
- user intent for this lane is explicit: `recipe` should become `sandbox template`

So replay-25 is not inventing a new direction. It is inventorying an already
declared direction that the codebase has not consistently applied.

## The Actual Ambiguity

There are three distinct rename scopes hiding inside the single phrase
"rename recipe to sandbox template."

### A. User-visible wording only

Change:

- labels
- toasts
- component titles
- marketplace/detail wording

But keep:

- resource type `"recipe"`
- backend request fields like `recipe_id`
- frontend API/types like `RecipeSnapshot`

This is the narrowest move, but it is mostly cosmetic.

### B. Outward contract rename

Change:

- owner-facing backend request/response naming
- frontend API/types naming
- frontend page/component naming

But keep:

- library resource type `"recipe"`
- storage/repo contracts
- runtime/provider internals

This is the first non-cosmetic candidate.

### C. Full taxonomy + internal rename

Change all of:

- outward contract
- library resource type
- store keys / routes / editors
- backend service/resource taxonomy
- storage/repo naming

This is the most honest end state, but it is much larger than the current lane
size that replay-22 through replay-24 used.

## Recommended Ruling

### 1. Replay-25 should stay inventory-only

This residue crosses:

- backend outward contract
- frontend API/types
- library taxonomy
- component naming
- backend internal/service naming

That is too wide to rename by inertia.

### 2. The first implementation lane should likely target outward contract before taxonomy

Recommended first cut after replay-25:

- rename user-visible/frontend/API concept toward `sandbox template`
- keep library resource type `"recipe"` temporarily internal

Reason:

- it makes product and owner-facing contract more truthful
- it avoids mixing outward rename with library/storage taxonomy in one jump

### 3. Library resource type rename should be a separate later lane

Changing `"recipe"` as a resource type would also touch:

- backend library CRUD dispatch
- frontend store keys
- router paths
- detail/editor routing
- test fixtures across marketplace/library surfaces

That deserves its own checkpoint after the outward rename is settled.

### 4. Runtime/resource lease truth remains completely out of lane

Replay-25 must not mix this rename with:

- `lease_id`
- monitor/session/terminal surfaces
- runtime provider snapshots
- sandbox binding semantics

Those are unrelated truths.

## Proposed Classification Output

Replay-25 should explicitly produce three buckets.

### Bucket 1. Outward rename candidates

Likely in-scope for the first implementation lane:

- `CreateThreadRequest.recipe_id`
- `SaveThreadLaunchConfigRequest.recipe_id`
- `ThreadLaunchConfig.recipe_id`
- `ThreadLaunchConfig.recipe`
- `CreateThreadOptions.recipeId`
- `RecipeSnapshot`
- `RecipeEditor`
- `selectedRecipeId`
- outward UI copy that still says recipe

### Bucket 2. Taxonomy/internal rename candidates

Should likely wait for a later checkpoint:

- `list_library("recipe", ...)`
- `create_resource("recipe", ...)`
- `update/delete_resource("recipe", ...)`
- `LibraryType = ... | "recipe"`
- `libraryRecipes`
- `/library/recipe/:id`

### Bucket 3. Protected truths / not in lane

Must not be renamed by replay-25 or its first follow-up:

- runtime/resource `lease_id`
- provider/runtime payload shape not tied to sandbox-template naming
- schema/migration/storage repair work
- sandbox binding semantics

## Proposed Next Checkpoint

Recommended next implementation checkpoint after replay-25:

`database-refactor-dev-replay-26-outward-sandbox-template-contract-cleanup`

Target shape:

- user-visible and owner-facing contract stops saying `recipe`
- library resource taxonomy may still internally say `"recipe"` for one more lane
- no long-lived alias sprawl unless focused RED proves a short bridge is truly
  required

## Stopline

Replay-25 does **not** authorize:

- resource type rename from `"recipe"` to another key
- route migration from `/library/recipe/...`
- storage/repo contract rename
- runtime/provider payload redesign
- SQL/migrations/live DB writes
- schema changes
- broad marketplace redesign
- any implementation code change beyond doc/ruling

## Open Question For Ruling

Is replay-25 the right checkpoint to classify the current `recipe` residue into
outward contract, taxonomy/internal, and protected-truth buckets, so that the
next implementation lane can first clean the user-facing and owner-facing
`sandbox template` contract without yet renaming the underlying library
resource type?
