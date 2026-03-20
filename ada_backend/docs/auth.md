# Authentication & Authorization

Draft'n Run uses three authentication mechanisms and a four-tier role hierarchy. Users and organizations are managed by Supabase; all other resources are managed by the backend.

## Authentication Mechanisms

### 1. Supabase JWT (primary)

The main auth for dashboard users and the MCP server. Every API request from the frontend or MCP carries a Supabase-issued JWT in `Authorization: Bearer <jwt>`.

**Validation** (`get_user_from_supabase_token` in `routers/auth_router.py`):
- Extracts the Bearer token from the `Authorization` header
- Calls `supabase.auth.get_user(token)` to validate server-side
- Returns `SupabaseUser(id, email, token)`
- Sets user in request context for downstream dependencies

**Failure responses**: 401 with specific messages for expired tokens, invalid format, or Supabase errors.

### 2. Scoped API Keys (project & organization)

User-generated keys for programmatic access. Sent via `X-API-Key` header.

**Generation** (`services/api_key_service.py`):
1. 24 random bytes (192 bits) via `secrets.token_bytes(24)`
2. Base64url-encoded, stripped of padding
3. Prefixed with `taylor_` → result: `taylor_<32 base64url chars>`
4. Salted hash for storage: `SHA-256(raw_key + BACKEND_SECRET_KEY)` — only the hex digest is stored

**Scope types**:
- `ProjectApiKey` — scoped to a single project (used for `/projects/{id}/{env}/run`)
- `OrgApiKey` — scoped to an organization (used for any org-level endpoint)

**Verification** (`verify_api_key_dependency`): Hashes the incoming key, looks up in `api_keys` table, checks `is_active`, resolves scope.

### 3. Internal Service Keys (pre-shared)

For service-to-service communication between workers and the API. Three separate headers, each verified against a pre-hashed value from settings:

| Header | Settings field | Used by |
|---|---|---|
| `X-Ingestion-API-Key` | `INGESTION_API_KEY_HASHED` | `source_router` (data source creation) |
| `X-Webhook-API-Key` | `WEBHOOK_API_KEY_HASHED` | `webhook_internal_router` (all endpoints) |
| `X-Admin-API-Key` | `ADMIN_KEY_HASHED` | `credits_router` (org limits) |

All use the same `_hash_key()` function (salted SHA-256).

## Role Hierarchy

```python
class UserRights(Enum):
    SUPER_ADMIN = ("super-admin",)
    ADMIN = ("super-admin", "admin")
    DEVELOPER = ("super-admin", "admin", "developer")
    MEMBER = ("super-admin", "admin", "developer", "member")
```

Each level is a tuple of **all roles that satisfy the check** (inclusive upward):
- **super-admin** — global admin, can manage components, LLM models, credits, all orgs
- **admin** — organization admin, can manage secrets, API keys, variable definitions
- **developer** — can create/modify projects, graphs, deploy, manage integrations
- **member** — read-only access to projects, runs, traces, dashboards

## Auth Dependency Factories

All defined in `routers/auth_router.py`:

| Factory | Checks | Used on |
|---|---|---|
| `user_has_access_to_project_dependency(roles)` | JWT + project → org → Edge Function role check | Most project endpoints |
| `user_has_access_to_organization_dependency(roles)` | JWT + org → Edge Function role check | Org-scoped endpoints |
| `user_has_access_to_organization_xor_verify_api_key(roles)` | JWT **or** `X-API-Key` (not both) | Dual-auth endpoints (projects, variables, OAuth) |
| `ensure_super_admin_dependency()` | JWT → Edge Function super-admin check | Admin endpoints |
| `verify_api_key_dependency` | `X-API-Key` → hash + DB lookup | External API endpoints |
| `super_admin_or_admin_api_key_dependency` | JWT super-admin **or** `X-Admin-API-Key` | Credits endpoints |

## Edge Functions

Organization access is checked via Supabase Edge Functions (remote HTTP calls), **not local DB queries**:

| Edge Function | Purpose |
|---|---|
| `check-org-access` | Returns `{access: bool, role: string}` for user + org |
| `check-super-admin` | Returns `{is_super_admin: bool}` for user |

Both receive the user's JWT in `Authorization: Bearer` and are called via `httpx.AsyncClient` with a 10s timeout.

## WebSocket Authentication

For real-time run streaming (`/ws/runs/{run_id}`):

1. Extract token from `Authorization: Bearer` header **or** `?token=` query parameter
2. Validate via `get_user_from_supabase_token()` (same as HTTP)
3. Check project access via `user_has_access_to_project_dependency(MEMBER)`
4. Custom close codes: `4401` (unauthorized), `4403` (forbidden), `4404` (not found), `4510` (Redis unavailable)

## OFFLINE_MODE

For local development without Supabase:

```env
OFFLINE_MODE=True
OFFLINE_DEFAULT_ROLE=admin
```

Three bypass points:
1. `get_user_from_supabase_token()` → returns dummy user (`id=11111111-...`, `email=dummy@email.com`)
2. `get_user_access_to_organization()` → skips Edge Function, returns requested org with `OFFLINE_DEFAULT_ROLE`
3. `is_user_super_admin()` → always returns `True`

## CORS

Global CORS middleware in `main.py`:
- Origins: `CORS_ALLOW_ORIGINS` (comma-separated). **Must be explicit origins** (e.g. `https://app.draftnrun.com,http://localhost:3000`) — a wildcard `*` is not permitted when `Access-Control-Allow-Credentials` is `true`.
- Credentials: allowed
- Methods/headers: all allowed

Widgets have per-widget origin allowlists stored in `widget.config["allowed_origins"]` with wildcard subdomain support.

## Key Files

- `ada_backend/routers/auth_router.py` — dependencies, API key endpoints, role enum
- `ada_backend/services/api_key_service.py` — key generation, hashing, verification
- `ada_backend/services/user_roles_service.py` — Edge Function calls
- `ada_backend/schemas/auth_schema.py` — Pydantic schemas
