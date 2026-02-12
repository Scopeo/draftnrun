# Variable Sets at Org Level

## Decision Log

- Variables are scoped to **org** (`organization_id NOT NULL`)
- `project_id` is **nullable** — reserved for future project-level scoping
- No merge logic (org + project) for now — YAGNI
- No check constraint needed since `organization_id` is always set
- Unique index: `(organization_id, set_id)` — not partial
- Scopeo (project-level variable sets) doesn't exist yet — this PR introduces variable sets for the first time
- OAuth connection UUIDs are stored as variable values, resolved to tokens at runtime

## Model: `ProjectVariableSet`

Table: `project_variable_sets`

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | UUID | NO | PK |
| organization_id | UUID | NO | Security boundary, indexed |
| project_id | UUID | YES | Future use |
| set_id | String | NO | User-defined key (e.g. user ID) |
| values | JSONB | NO | Key-value pairs |
| created_at | DateTime | NO | server_default=now() |
| updated_at | DateTime | NO | server_default=now(), onupdate |

Constraints:
- `uq_org_variable_set`: UNIQUE(organization_id, set_id)
- `uq_project_variable_set`: UNIQUE(project_id, set_id) WHERE project_id IS NOT NULL — for future project-scoped sets

## Org-Level CRUD (Repository)

File: `ada_backend/repositories/variable_sets_repository.py`

- `get_org_variable_set(session, organization_id, set_id) -> ProjectVariableSet | None`
- `list_org_variable_sets(session, organization_id) -> list[ProjectVariableSet]`
- `upsert_org_variable_set(session, organization_id, set_id, values) -> ProjectVariableSet`
- `delete_org_variable_set(session, organization_id, set_id) -> bool`

## Org-Level Endpoints (Router)

File: `ada_backend/routers/project_router.py`

Auth: API key (`verify_api_key_dependency`), org-scoped key required.

Helper: `_verify_org_access(organization_id, verified_api_key)` — checks `verified_api_key.organization_id == organization_id`, rejects project-scoped keys.

| Method | Path | Action |
|--------|------|--------|
| GET | `/org/{organization_id}/variable-sets` | List all org sets |
| GET | `/org/{organization_id}/variable-sets/{set_id}` | Get one |
| PUT | `/org/{organization_id}/variable-sets/{set_id}` | Upsert |
| DELETE | `/org/{organization_id}/variable-sets/{set_id}` | Delete |

## Run Endpoint Changes

File: `ada_backend/routers/project_router.py` (run endpoint)

When `set_id` is provided in input_data:
1. Load org variable set by `project.organization_id` + `set_id`
2. Use values as variable overrides
3. For oauth-type variables: resolve UUID to access token via Nango

## OAuth Variable Resolution

After loading variable values, for each variable definition with `type == "oauth"`:
1. Get `provider_config_key` from definition metadata
2. Look up the connection UUID from resolved values
3. Call Nango to get fresh access token
4. Replace UUID with token in resolved values

## Implementation Order

1. Migration: create `project_variable_sets` table
2. Model: add `ProjectVariableSet` to models.py
3. Repository: org-level CRUD functions
4. Schema: response models
5. Router: org-level endpoints + auth helper
6. Run endpoint: variable set loading + OAuth resolution
7. Test with curl

## Files Changed (DNR side)

- `ada_backend/database/alembic/versions/<new>_create_variable_sets_table.py` (NEW)
- `ada_backend/database/models.py` (ADD ProjectVariableSet)
- `ada_backend/repositories/project_variable_sets_repository.py` (NEW)
- `ada_backend/schemas/project_schema.py` (ADD response models)
- `ada_backend/routers/project_router.py` (ADD org endpoints + run changes)
