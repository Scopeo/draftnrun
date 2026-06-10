# Webhooks

Draft'n Run has three webhook patterns: provider webhooks (external services pushing events), user-triggered webhooks (API users triggering runs), and internal webhooks (worker-to-API calls).

## Pattern 1: Provider Webhooks

**Router**: `routers/webhooks/provider_webhooks_router.py`

External services (Aircall, Resend, Typeform) push events directly to the backend:

| Endpoint | Provider | Verification |
| --- | --- | --- |
| `POST /webhooks/aircall` | Aircall | Token in payload |
| `POST /webhooks/resend` | Resend | Svix signature header |
| `POST /webhooks/typeform/{webhook_id}` | Typeform | `Typeform-Signature` HMAC SHA-256 header over the raw request body |

Provider endpoints:

1. Verify provider-specific signature/token
2. Deduplicate via Redis SET NX with TTL (`check_and_set_webhook_event`)
3. Push to Redis Stream (`REDIS_WEBHOOK_STREAM`) via XADD

Raw-body signatures, such as Typeform's HMAC header, are verified before parsing JSON so malformed unauthenticated payloads are rejected by the signature check first.
Webhook service failures, including signature, configuration, not-found, and queueing errors, propagate as `ServiceError` subclasses and are translated by the global error handler.

**Providers** (enum `WebhookProvider`): `resend`, `aircall`, `slack`, `typeform`, `direct_trigger`.

Typeform setup is project-scoped via `POST /projects/{project_id}/webhooks/typeform` (developer role). The setup response returns a `callback_url` and a `signing_secret` when a webhook is created or rotated. The callback URL is built from `ADA_URL`; setup fails if `ADA_URL` is not configured so webhooks cannot be pointed at the wrong environment. Paste the callback URL into Typeform's webhook URL and the signing secret into Typeform's webhook secret field. Existing webhooks do not return the stored secret again unless `rotate_secret=true`.

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
| --- | --- |
| `POST /internal/webhooks/{webhook_id}/execute` | Resolve triggers, prepare input, run workflows |
| `POST /internal/webhooks/projects/{project_id}/envs/{env}/run` | Enqueue workflow run to durable Redis run queue (202). Accepts optional `run_id` query param to reuse a pre-created run; body may include `cron_id` for scheduler correlation and `cron_run_id` for top-level scheduler-owned executions. The RunQueueWorker picks up and executes the run with heartbeat-based orphan recovery. |
| `PATCH /internal/webhooks/projects/{project_id}/runs/{run_id}/fail` | Mark a pre-created run as FAILED (called by worker on dead-letter). Validates project ownership. |

Authenticated via `X-Webhook-API-Key` (internal service key).

For scheduler-triggered calls, always pass `cron_id` (job id) in the body so the `RunQueueWorker` keeps the cron correlation
in tracing context. Pass `cron_run_id` (execution id) only for the top-level scheduler-owned execution; the `RunQueueWorker`
handles CronRun state transitions (QUEUED→RUNNING→COMPLETED/ERROR). Endpoint-polling fan-out runs forward `cron_id` without
reusing the parent `cron_run_id`.

`WebhookExecuteResult.run_id` is a UUID (nullable), serialized as a UUID string in JSON responses.

Provider webhook workflow input is prepared by `services/webhooks/webhook_service.py`. For default providers such as
Aircall and Typeform, the original webhook payload fields are passed through at the top level and the same raw payload is
also serialized into a single user `messages` entry. Do not add a nested `webhook_payload` copy. Resend is provider-specific:
it fetches email content from the Resend API and passes the formatted email fields instead of the raw event body.

## Event Routing

### Provider webhooks (Aircall, Resend, Typeform)

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
    → API enqueues run to durable Redis run queue (RunQueueWorker)
    → RunQueueWorker picks up → PENDING→RUNNING→COMPLETED/FAILED with heartbeat-based orphan recovery
    → Worker still marks run FAILED via /fail on dead-letter before execution starts
  → If dead-lettered: PATCH /internal/webhooks/projects/{project_id}/runs/{run_id}/fail → Run marked FAILED
```

## Delivery ACK semantics (Layer B)

Webhook stream workers use **outcome-based ACK**: ACK only when processing is terminal for that attempt.

- Success -> ACK (`message_ack_success`)
- Fatal/non-retryable failure -> ACK (`message_ack_fatal`)
- Retryable failure -> no ACK (`message_retry_scheduled`) so the message stays pending for redelivery
- If delivery attempts reach `MAX_DELIVERY_ATTEMPTS`, the message is dead-lettered and ACKed

### Retry/fatal classification

`webhook_scripts/webhook_main.py` emits a failure classification marker consumed by `WebhookWorker`:

- `WEBHOOK_FAILURE_CLASS=retryable`: network errors and HTTP `429`/`5xx`
- `WEBHOOK_FAILURE_CLASS=fatal`: deterministic client/data errors (for example malformed direct-trigger payload)

The worker maps these markers to processing outcomes and applies ACK policy accordingly.

## Data Model

- **`Webhook`** (`webhooks`): `organization_id`, `provider`, `external_client_id`, `encrypted_signing_secret` (nullable, used by Typeform). Indexed by `(provider, external_client_id)`.
- **`IntegrationTrigger`** (`integration_triggers`): Links webhook → project. Has `events` (JSONB), `events_hash`, `enabled`, `filter_options` (JSONB). Unique on `(webhook_id, events_hash, project_id)`.
- **`Run`** (`runs`): `event_id` (nullable) links the run back to the originating webhook event. For direct triggers, the Run is created before enqueue so it's visible in DB throughout the entire lifecycle.

## Filter System

`FilterExpression` supports nested AND/OR conditions with operators: `equals`, `contains`. Evaluated against the webhook payload JSON in `webhook_service.evaluate_filter()`.

## Run Failure Alerting

When a webhook- or cron-triggered run transitions to `FAILED`, an email alert is sent via the Resend API to configured recipients.

### How it works

1. `update_run_status()` and `fail_pending_run()` in `services/run_service.py` call `maybe_send_run_failure_alert()` when the new status is `FAILED`.
2. The alert service checks the run's `trigger` — only `WEBHOOK` and `CRON` triggers fire alerts.
3. It queries `project_alert_emails` for the project's configured recipient list.
4. If recipients exist and `RESEND_API_KEY` + `RESEND_FROM_EMAIL` are set, it sends the email in a background thread (fire-and-forget).
5. All exceptions are caught and logged — alerting never breaks run processing.

### Configuration

- **Settings**: `RESEND_API_KEY` (existing) and `RESEND_FROM_EMAIL` must both be set. If either is missing, alerting silently no-ops.
- **Recipients**: Managed per project via the CRUD API at `GET/POST/DELETE /projects/{project_id}/alert-emails`.
- **DB table**: `project_alert_emails` with unique constraint on `(project_id, email)`.

## Key Files

- `routers/webhooks/provider_webhooks_router.py` — Aircall, Resend, Typeform receiver endpoints
- `routers/webhooks/webhook_config_router.py` — Typeform setup endpoint
- `routers/webhooks/webhook_trigger_router.py` — user-triggered webhook
- `routers/webhooks/webhook_internal_router.py` — worker-called endpoints
- `routers/alert_email_router.py` — CRUD for alert email recipients
- `services/webhooks/webhook_service.py` — execution, filtering, input preparation
- `services/webhooks/typeform_service.py` — Typeform signature verification and event IDs
- `services/webhooks/typeform_setup_service.py` — Typeform webhook setup
- `services/alerting/alert_service.py` — run failure alert logic
- `services/alerting/email_service.py` — Resend email sending wrapper
- `schemas/webhook_schema.py` — Pydantic schemas
