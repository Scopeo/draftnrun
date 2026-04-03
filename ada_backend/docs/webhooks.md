# Webhooks

Draft'n Run has three webhook patterns: provider webhooks (external services pushing events), user-triggered webhooks (API users triggering runs), and internal webhooks (worker-to-API calls).

## Pattern 1: Provider Webhooks

**Router**: `routers/webhooks/provider_webhooks_router.py`

External services (Aircall, Resend) push events directly to the backend:

| Endpoint | Provider | Verification |
|---|---|---|
| `POST /webhooks/aircall` | Aircall | Token in payload |
| `POST /webhooks/resend` | Resend | Svix signature header |

Both endpoints:
1. Verify provider-specific signature/token
2. Deduplicate via Redis SET NX with TTL (`check_and_set_webhook_event`)
3. Push to Redis Stream (`REDIS_WEBHOOK_STREAM`) via XADD

**Providers** (enum `WebhookProvider`): `resend`, `aircall`, `slack`, `direct_trigger`.

## Pattern 2: User-Triggered Webhooks

**Router**: `routers/webhooks/webhook_trigger_router.py`

API users trigger workflow runs via webhook:

- `POST /webhooks/trigger/{project_id}/envs/{env}` — authenticated via project `X-API-Key`
- Supports idempotency via `event_id` query param
- Returns 202 (async), queues to the same Redis stream

## Pattern 3: Internal Webhooks

**Router**: `routers/webhooks/webhook_internal_router.py`

Called by the webhook worker after consuming from the Redis stream:

| Endpoint | Purpose |
|---|---|
| `POST /internal/webhooks/{webhook_id}/execute` | Resolve triggers, prepare input, run workflows |
| `POST /internal/webhooks/projects/{project_id}/envs/{env}/run` | Enqueue workflow run (202). Accepts optional `run_id` query param to reuse a pre-created run |
| `PATCH /internal/webhooks/projects/{project_id}/runs/{run_id}/fail` | Mark a pre-created run as FAILED (called by worker on dead-letter). Validates project ownership. |

Authenticated via `X-Webhook-API-Key` (internal service key).

`WebhookExecuteResult.run_id` is a UUID (nullable), serialized as a UUID string in JSON responses.

## Event Routing

### Provider webhooks (Aircall, Resend)

```text
Provider → POST /webhooks/{provider}
  → Dedup (Redis SET NX)
  → XADD to Redis Stream
  → Webhook Worker picks up
  → Subprocess calls POST /internal/webhooks/{webhook_id}/execute
    → Resolve IntegrationTriggers
    → For each trigger:
      → Evaluate filter
      → run_with_tracking() → creates Run (PENDING→RUNNING→COMPLETED/FAILED)
      → Run.event_id links back to the original webhook event
```

### Direct triggers (user-triggered)

```text
API user → POST /webhooks/trigger/{project_id}/envs/{env}
  → Dedup (Redis SET NX)
  → Create Run (PENDING) in DB ← run exists BEFORE Redis enqueue
  → Persist direct-trigger input in `run_inputs` (keyed by `retry_group_id=run_id`) before Redis enqueue
  → XADD to Redis Stream (payload includes run_id)
  → Webhook Worker picks up
  → Subprocess calls POST /internal/webhooks/projects/{project_id}/envs/{env}/run?run_id=...
    → Reuses existing Run row
    → API executes run as FastAPI background task (same behavior as main baseline)
    → Worker still marks run FAILED via /fail on dead-letter before execution starts
  → If dead-lettered: PATCH /internal/webhooks/projects/{project_id}/runs/{run_id}/fail → Run marked FAILED
```

## Data Model

- **`Webhook`** (`webhooks`): `organization_id`, `provider`, `external_client_id`. Indexed by `(provider, external_client_id)`.
- **`IntegrationTrigger`** (`integration_triggers`): Links webhook → project. Has `events` (JSONB), `events_hash`, `enabled`, `filter_options` (JSONB). Unique on `(webhook_id, events_hash, project_id)`.
- **`Run`** (`runs`): `event_id` (nullable) links the run back to the originating webhook event. For direct triggers, the Run is created before enqueue so it's visible in DB throughout the entire lifecycle.

## Filter System

`FilterExpression` supports nested AND/OR conditions with operators: `equals`, `contains`. Evaluated against the webhook payload JSON in `webhook_service.evaluate_filter()`.

## Key Files

- `routers/webhooks/provider_webhooks_router.py` — Aircall, Resend endpoints
- `routers/webhooks/webhook_trigger_router.py` — user-triggered webhook
- `routers/webhooks/webhook_internal_router.py` — worker-called endpoints
- `services/webhooks/webhook_service.py` — execution, filtering, input preparation
- `schemas/webhook_schema.py` — Pydantic schemas
