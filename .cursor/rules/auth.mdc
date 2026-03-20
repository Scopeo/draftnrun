---
globs:
  - ada_backend/routers/auth_router.py
  - ada_backend/services/user_roles_service.py
  - ada_backend/services/api_key_service.py
---

## Auth System Conventions

- Three auth mechanisms: Supabase JWT, project/org API keys (`X-API-Key`), internal service keys.
- Four role tiers: `SUPER_ADMIN > ADMIN > DEVELOPER > MEMBER` (each includes all below).
- Use the correct auth dependency factory — never manual token parsing:
  - `user_has_access_to_project_dependency(roles)` — project endpoints
  - `user_has_access_to_organization_dependency(roles)` — org endpoints
  - `user_has_access_to_organization_xor_verify_api_key(roles)` — dual-auth (JWT or API key)
  - `ensure_super_admin_dependency()` — admin endpoints
  - `verify_api_key_dependency` — external API-key-only endpoints
- Org access is checked via Supabase Edge Functions (remote HTTP call), NOT local DB.
- API key generation: 192-bit random, base64url, prefix `taylor_`, stored as `SHA-256(key + BACKEND_SECRET_KEY)`.
- `OFFLINE_MODE` bypass exists for local dev (returns dummy user with configurable role).
- See `ada_backend/docs/auth.md` for full documentation.
