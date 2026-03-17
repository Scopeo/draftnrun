# API Reference

Complete endpoint reference for the Draft'n Run backend.

**Auth legend**: JWT(Role) = Supabase JWT with role check · JWT|ApiKey(Role) = either JWT or `X-API-Key` · ApiKey = `X-API-Key` only · IngestionKey = `X-Ingestion-API-Key` · WebhookKey = `X-Webhook-API-Key` · SuperAdmin|AdminKey = JWT super-admin or `X-Admin-API-Key` · Public = no auth

## Auth & API Keys (`auth_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/auth/api-key` | JWT(Member) | List project API keys |
| POST | `/auth/api-key` | JWT(Developer) | Create project API key |
| DELETE | `/auth/api-key` | JWT(Admin) | Revoke project API key |
| GET | `/auth/org-api-key` | JWT(Member) | List org API keys |
| POST | `/auth/org-api-key` | JWT(Admin) | Create org API key |
| DELETE | `/auth/org-api-key` | JWT(Admin) | Revoke org API key |

## Projects (`project_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/org/{organization_id}` | JWT\|ApiKey(Member) | List projects for org |
| GET | `/projects/{project_id}` | JWT(Member) | Get project |
| POST | `/projects/{organization_id}` | JWT(Developer) | Create workflow |
| PATCH | `/projects/{project_id}` | JWT(Developer) | Update project |
| DELETE | `/projects/{project_id}` | JWT(Developer) | Delete project |
| POST | `/projects/{project_id}/{env}/run` | ApiKey | Run via API key (by env) |
| POST | `/projects/{project_id}/{env}/chat` | JWT(Member) | Chat by env |
| POST | `/projects/{project_id}/graphs/{graph_runner_id}/chat` | JWT(Member) | Chat with specific graph |
| POST | `/projects/{project_id}/graphs/{graph_runner_id}/chat/async` | JWT(Member) | Async chat (202) |

## Graphs (`graph_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/{project_id}/graph/{graph_runner_id}` | JWT(Member) | Get graph |
| PUT | `/projects/{project_id}/graph/{graph_runner_id}` | JWT(Developer) | Replace graph |
| POST | `/projects/{project_id}/graph/{graph_runner_id}/deploy` | JWT(Developer) | Deploy graph |
| PUT | `/projects/{project_id}/graph/{graph_runner_id}/env/{env}` | JWT(Developer) | Bind to environment |
| POST | `/projects/{project_id}/graph/{graph_runner_id}/save-version` | JWT(Developer) | Save version |
| POST | `/projects/{project_id}/graph/{graph_runner_id}/load-as-draft` | JWT(Developer) | Load as draft |
| GET | `/projects/{project_id}/graph/{graph_runner_id}/modification-history` | JWT(Member) | Modification history |
| GET | `/projects/{project_id}/graph/{graph_runner_id}/field-expressions/autocomplete` | JWT(Member) | Autocomplete |
| GET | `/projects/{project_id}/graph/{graph_runner_id}/load-copy` | JWT(Developer) | Load copy |
| DELETE | `/projects/{project_id}/graph/{graph_runner_id}` | JWT(Developer) | Delete graph |

## Runs (`run_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/{project_id}/runs` | JWT(Member) | List runs (paginated) |
| POST | `/projects/{project_id}/runs` | JWT(Member) | Create run |
| GET | `.../runs/{run_id}` | JWT(Member) | Get run |
| GET | `.../runs/{run_id}/result` | JWT(Member) | Get run result |
| PATCH | `.../runs/{run_id}` | JWT(Member) | Update run status |

## WebSocket (`run_stream_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| WS | `/ws/runs/{run_id}` | JWT | Stream run events |

## Agents (`agent_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/org/{organization_id}/agents` | JWT(Member) | List agents |
| GET | `/agents/{project_id}/versions/{graph_runner_id}` | JWT(Member) | Get agent version |
| POST | `/org/{organization_id}/agents` | JWT(Developer) | Create agent |
| PUT | `/agents/{project_id}/versions/{graph_runner_id}` | JWT(Developer) | Update agent |

## Organization (`organization_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/org/{organization_id}/secrets` | JWT\|ApiKey(Member) | List secrets |
| PUT | `/org/{organization_id}/secrets/{key}` | JWT\|ApiKey(Admin) | Upsert secret |
| DELETE | `/org/{organization_id}/secrets/{key}` | JWT\|ApiKey(Admin) | Delete secret |

## Variables (`variables_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/org/{organization_id}/variable-definitions` | JWT\|ApiKey(Member) | List definitions |
| PUT | `.../variable-definitions/{name}` | JWT\|ApiKey(Admin) | Upsert definition |
| DELETE | `.../variable-definitions/{name}` | JWT\|ApiKey(Admin) | Delete definition |
| GET | `/org/{organization_id}/variable-sets` | JWT\|ApiKey(Member) | List sets |
| GET | `.../variable-sets/{set_id}` | JWT\|ApiKey(Member) | Get set |
| PUT | `.../variable-sets/{set_id}` | JWT\|ApiKey(Admin) | Upsert set |
| DELETE | `.../variable-sets/{set_id}` | JWT\|ApiKey(Admin) | Delete set |

## Knowledge (`knowledge_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/knowledge/organizations/{org_id}/sources/{source_id}/documents` | JWT(Member) | List documents |
| GET | `.../documents/{document_id}` | JWT(Member) | Get document + chunks |
| PUT | `.../documents/{document_id}` | JWT(Developer) | Update document chunks |
| DELETE | `.../documents/{document_id}` | JWT(Developer) | Delete document |
| DELETE | `.../chunks/{chunk_id}` | JWT(Developer) | Delete chunk |

## Sources (`source_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/sources/{organization_id}` | JWT(Member) | List sources |
| POST | `/sources/{organization_id}` | IngestionKey | Create source |
| POST | `/sources/{organization_id}/{source_id}` | JWT\|ApiKey(Developer) | Update source |
| DELETE | `/sources/{organization_id}/{source_id}` | JWT(Developer) | Delete source |
| GET | `/organizations/{org_id}/sources/{source_id}/usage` | JWT(Member) | Check source usage |

## QA Datasets (`quality_assurance_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/{project_id}/qa/datasets` | JWT(Member) | List datasets |
| POST | `.../qa/datasets` | JWT(Developer) | Create datasets |
| PATCH | `.../qa/datasets/{dataset_id}` | JWT(Developer) | Update dataset |
| DELETE | `.../qa/datasets` | JWT(Developer) | Delete datasets |
| GET | `.../datasets/{dataset_id}/entries` | JWT(Member) | List entries |
| POST | `.../datasets/{dataset_id}/entries` | JWT(Developer) | Create entries |
| PATCH | `.../datasets/{dataset_id}/entries` | JWT(Developer) | Update entries |
| DELETE | `.../datasets/{dataset_id}/entries` | JWT(Developer) | Delete entries |
| POST | `.../datasets/{dataset_id}/run` | JWT(Member) | Run QA |
| POST | `.../entries/from-history` | JWT(Developer) | Trace → QA entry |
| GET | `.../datasets/{dataset_id}/export` | JWT(Member) | Export CSV |
| POST | `.../datasets/{dataset_id}/import` | JWT(Developer) | Import CSV |

## QA Judges (`llm_judges_router.py`, `qa_evaluation_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/projects/{project_id}/qa/llm-judges` | JWT(Member) | List judges |
| GET | `/qa/llm-judges/defaults` | JWT | Get judge defaults |
| POST | `.../qa/llm-judges` | JWT(Developer) | Create judge |
| PATCH | `.../qa/llm-judges/{judge_id}` | JWT(Developer) | Update judge |
| DELETE | `.../qa/llm-judges` | JWT(Developer) | Delete judges |
| POST | `.../llm-judges/{judge_id}/evaluations/run` | JWT(Member) | Run evaluation |
| GET | `.../version-outputs/{vo_id}/evaluations` | JWT(Member) | Get evaluations |

## Monitoring (`monitor_router.py`, `trace_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/monitor/org/{organization_id}/charts` | JWT(Member) | Org charts |
| GET | `/monitor/org/{organization_id}/kpis` | JWT(Member) | Org KPIs |
| GET | `/projects/{project_id}/traces` | JWT(Member) | List traces |
| GET | `/traces/{trace_id}/tree` | JWT | Trace span tree |

## Cron Jobs (`cron_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/organizations/{org_id}/crons` | JWT(Member) | List crons |
| GET | `.../crons/{cron_id}` | JWT(Member) | Get cron |
| POST | `/organizations/{org_id}/crons` | JWT(Developer) | Create cron |
| PATCH | `.../crons/{cron_id}` | JWT(Developer) | Update cron |
| DELETE | `.../crons/{cron_id}` | JWT(Developer) | Delete cron |
| POST | `.../crons/{cron_id}/pause` | JWT(Developer) | Pause |
| POST | `.../crons/{cron_id}/resume` | JWT(Developer) | Resume |
| GET | `.../crons/{cron_id}/runs` | JWT(Member) | Cron history |

## Webhooks

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/webhooks/trigger/{project_id}/envs/{env}` | ApiKey | User-triggered webhook |
| POST | `/webhooks/aircall` | Public | Aircall provider webhook |
| POST | `/webhooks/resend` | Public | Resend provider webhook |
| POST | `/internal/webhooks/{webhook_id}/execute` | WebhookKey | Internal: execute webhook |
| POST | `/internal/webhooks/projects/{project_id}/envs/{env}/run` | WebhookKey | Internal: enqueue run |

## Widgets (`widget_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/widget/{widget_key}/config` | Public | Widget public config |
| POST | `/widget/{widget_key}/chat` | Public | Widget chat |
| GET | `/org/{organization_id}/widgets` | JWT(Member) | List widgets |
| GET | `/widgets/{widget_id}` | JWT | Get widget |
| GET | `/widgets/project/{project_id}` | JWT | Widget by project |
| POST | `/org/{organization_id}/widgets` | JWT(Developer) | Create widget |
| PATCH | `/widgets/{widget_id}` | JWT(Developer) | Update widget |
| POST | `/widgets/{widget_id}/regenerate-key` | JWT(Admin) | Regenerate key |
| DELETE | `/widgets/{widget_id}` | JWT(Admin) | Delete widget |

## OAuth Connections (`oauth_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/organizations/{org_id}/oauth-connections` | JWT\|ApiKey(Developer) | List connections |
| POST | `.../oauth-connections/authorize` | JWT\|ApiKey(Developer) | Start OAuth flow |
| POST | `/organizations/{org_id}/oauth-connections` | JWT\|ApiKey(Developer) | Confirm connection |
| GET | `.../oauth-connections/status` | JWT\|ApiKey(Developer) | Check status |
| PATCH | `.../oauth-connections/{id}` | JWT\|ApiKey(Developer) | Update connection |
| DELETE | `.../oauth-connections/{id}` | JWT\|ApiKey(Developer) | Revoke connection |

## Integrations (`integration_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| PUT | `/project/{project_id}/integration/{integration_id}` | JWT(Developer) | Update integration |

## Templates (`template_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/templates/{organization_id}` | JWT(Member) | List templates |

## Ingestion Tasks (`ingestion_task_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/ingestion_task/{organization_id}` | JWT(Member) | List tasks |
| POST | `/ingestion_task/{organization_id}` | JWT\|ApiKey(Developer) | Create task |
| DELETE | `/ingestion_task/{organization_id}/{source_id}` | JWT(Developer) | Delete task |

## S3 Files (`s3_files_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/organizations/{org_id}/files/upload-urls` | JWT\|ApiKey(Developer) | Get presigned URLs |
| POST | `/files/{organization_id}/upload` | JWT(Developer) | Upload files |

## Credits (`credits_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/organizations/{org_id}/credit-usage` | JWT(Member) | Credit usage |
| GET | `/organizations-limits-and-usage` | JWT(SuperAdmin) | All org limits |
| POST | `/organizations/{org_id}/organization-limits` | SuperAdmin\|AdminKey | Create limit |
| PATCH | `.../organization-limits` | JWT(SuperAdmin) | Update limit |
| DELETE | `.../organization-limits` | JWT(SuperAdmin) | Delete limit |

## Components (`components_router.py`, `component_version_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/components/{organization_id}` | JWT(Member) | List org components |
| GET | `/components/` | JWT(SuperAdmin) | List all components |
| GET | `/components/fields/options` | JWT | Field options |
| PUT | `/components/{id}/versions/{version_id}/fields` | JWT(SuperAdmin) | Update version fields |

## Categories (`categories_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/categories` | JWT | List categories |
| POST | `/categories` | JWT(SuperAdmin) | Create category |
| PATCH | `/categories/{id}` | JWT(SuperAdmin) | Update category |
| DELETE | `/categories/{id}` | JWT(SuperAdmin) | Delete category |

## LLM Models (`llm_models_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/organizations/{org_id}/llm-models` | JWT(SuperAdmin) | List models |
| POST | `/organizations/{org_id}/llm-models` | JWT(SuperAdmin) | Create model |
| PATCH | `.../llm-models/{id}` | JWT(SuperAdmin) | Update model |
| DELETE | `.../llm-models/{id}` | JWT(SuperAdmin) | Delete model |

## Admin Tools (`admin_tools_router.py`, `global_secret_router.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/admin-tools/api-tools` | JWT(SuperAdmin) | Create API tool |
| GET | `/admin-tools/settings-secrets/` | JWT(SuperAdmin) | List global secrets |
| POST | `/admin-tools/settings-secrets/` | JWT(SuperAdmin) | Upsert global secret |
| DELETE | `/admin-tools/settings-secrets/{key}` | JWT(SuperAdmin) | Delete global secret |
