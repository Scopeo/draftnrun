# Credits & Billing

Draft'n Run tracks resource usage via a credit system with polymorphic cost models, per-project monthly aggregation, and organization-level limits.

## Cost Model

Polymorphic hierarchy on `EntityType` (`llm`, `component`, `parameter_value`):

### LLMCost

Per-token costs for LLM models. Fields: `credits_per_input_token`, `credits_per_output_token`. FK to `llm_models.id`.

### ComponentCost

Per-call or per-unit costs for components. Fields: `credits_per_call`, `credits_per` (JSONB). FK to `component_versions.id`.

### ParameterValueCost

Cost varies by parameter value. FK to `component_parameter_definitions.id` + `parameter_value`. Allows different costs for e.g. different model sizes within the same component.

## Usage Tracking

- **`Usage`** (`credits.usages`): Monthly aggregate per `(project_id, year, month)` with `credits_used`. Unique on project+year+month.
- **`SpanUsage`** (`credits.span_usages`): Per-span credit breakdown. FK to `traces.spans.span_id`. Fields: `credits_input_token`, `credits_output_token`, `credits_per_call`, `credits_per` (JSONB).

## Organization Limits

- **`OrganizationLimit`** (`credits.organization_limits`): Monthly credit cap per organization.
- Enforcement: checked before executing runs.

## API Endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /organizations/{org_id}/credit-usage` | JWT(Member) | Credit usage chart |
| `GET /organizations-limits-and-usage` | JWT(SuperAdmin) | All org limits + usage |
| `POST /organizations/{org_id}/organization-limits` | SuperAdmin\|AdminKey | Create org limit |
| `PATCH /organizations/{org_id}/organization-limits` | JWT(SuperAdmin) | Update org limit |
| `DELETE /organizations/{org_id}/organization-limits` | JWT(SuperAdmin) | Delete org limit |
| `PATCH /organizations/{org_id}/component-version-costs/{cv_id}` | JWT(SuperAdmin) | Upsert component cost |
| `DELETE /organizations/{org_id}/component-version-costs/{cv_id}` | JWT(SuperAdmin) | Delete component cost |

## Key Files

- `routers/credits_router.py` — API endpoints
- `services/credits_service.py` — business logic
- `repositories/credits_repository.py` — DB operations
- `database/models.py` — search for `LLMCost`, `ComponentCost`, `ParameterValueCost`, `Usage`, `SpanUsage`, `OrganizationLimit`
