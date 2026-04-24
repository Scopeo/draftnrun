# Quality Assurance System

The QA system enables testing workflows against datasets of input/groundtruth pairs, with LLM-based evaluation judges.

## Scoping

- **Datasets** and **LLM Judges** are **organization-scoped** — shared across all projects in an org.
- **QA Test Runs** (sessions) remain **project-scoped** — they test specific project versions.
- **Association tables** track which datasets/judges are used in which projects.

## Datasets

Datasets belong to an organization and contain input/groundtruth entries. Each dataset can have custom metadata columns. Datasets can be associated with multiple projects via the `dataset_project_associations` table.

- **`DatasetProject`** (`quality_assurance.dataset_project`): `organization_id`, `name`
- **`DatasetProjectAssociation`** (`quality_assurance.dataset_project_associations`): `dataset_id`, `project_id` (many-to-many)
- **`AssociationColumnMapping`** (`quality_assurance.association_column_mappings`): `association_id` FK → `dataset_project_associations.id`, `column_id` FK → `qa_dataset_metadata.column_id`, `role` (`ColumnRole` enum: `input` | `expected_output`). Unique on `(association_id, column_id)`. Tracks which dataset columns serve as inputs vs. expected outputs for each project association. Auto-populated from system columns when an association is created.
- **`QADatasetMetadata`** (`quality_assurance.qa_dataset_metadata`): column definitions per dataset. `dataset_id` FK → `dataset_project.id`, `column_id` (UUID, unique), `column_name`, `column_display_position`, `default_role` (`ColumnRole` enum, nullable — `input` | `expected_output` for system columns, `NULL` for user-created columns).
- **`InputGroundtruth`** (`quality_assurance.input_groundtruth`): dataset rows. `dataset_id` FK → `dataset_project.id`, `input` (JSONB), `groundtruth` (String, nullable), `position`. Also carries a legacy `custom_columns` (JSONB, nullable) field, but the canonical per-cell store is `DatasetCellValue`.
- **`DatasetCellValue`** (`quality_assurance.dataset_cell_values`): normalized per-cell storage — one row per (dataset-row, column) intersection. `row_id` FK → `input_groundtruth.id`, `column_id` FK → `qa_dataset_metadata.column_id`, `value` (Text, nullable). Unique on `(row_id, column_id)`.

### CRUD Endpoints (Organization-scoped)

- `GET /organizations/{organization_id}/qa/datasets` — list datasets
- `POST /organizations/{organization_id}/qa/datasets` — create datasets
- `PATCH /organizations/{organization_id}/qa/datasets/{dataset_id}` — rename
- `DELETE /organizations/{organization_id}/qa/datasets` — delete datasets
- `PUT /organizations/{organization_id}/qa/datasets/{dataset_id}/projects` — set project associations

## QA Run Process

### Sync

`POST /projects/{project_id}/qa/datasets/{dataset_id}/run`

1. Verify dataset is associated with the project and graph runner is bound to the same project
2. Select specific entries or all entries in the dataset
3. Execute the project's graph version against each entry's input
4. Store results as `VersionOutput` records (keyed by input + graph_runner_id, no session)
5. Return all results in the HTTP response (blocks until complete)

### Async (WebSocket streaming)

`POST /projects/{project_id}/qa/datasets/{dataset_id}/run/async` → 202 `{session_id, status}`

1. Validates entries, dataset ownership, and graph runner project binding; creates a `QASession` record (status=pending), returns 202 immediately
2. The QA job is pushed onto the Redis-backed QA queue (`ada_qa_queue`). A dedicated worker thread (same reliability pattern as the run queue — heartbeat, per-worker processing list, orphan recovery) picks up the job and processes entries sequentially:
   - Updates `QASession` status to `running` on start
   - Publishes events to Redis Pub/Sub channel `qa:{session_id}`
   - Updates `QASession` status to `completed`/`failed` with summary stats on finish
   - If the worker dies mid-job, the next pod recovers the orphaned item and resets the session to `pending`
3. Connect to `WS /ws/qa/{project_id}/{session_id}` to receive real-time events:
   - `qa.entry.started` `{input_id, index, total}` — entry processing begins
   - `qa.entry.completed` `{input_id, output, success, error}` — entry done
   - `qa.completed` `{summary}` — all entries processed (terminal, closes WS)
   - `qa.failed` `{error}` — unrecoverable error (terminal, closes WS)
4. Race-safe reconnect: the WS checks DB state on connect; if still in progress, it subscribes to Redis Pub/Sub then re-checks DB (with a fresh session) to catch completions that occurred during the subscription setup window. `stream_events` deduplicates `qa.entry.completed` events by `input_id` to handle the overlap between live Pub/Sub events and DB catch-up

Fully decoupled from the `runs` table. Uses a dedicated `QASession` model in the `quality_assurance` schema.

### QA Session History

- `GET /projects/{project_id}/qa/sessions` — list all QA sessions (optionally filtered by `dataset_id`)
- `GET /projects/{project_id}/qa/sessions/{qa_session_id}` — get a specific session's status and results

### Data Model

- **`QASession`** (`quality_assurance.qa_sessions`): `project_id`, `dataset_id`, `graph_runner_id`, `status` (pending/running/completed/failed), `total`, `passed`, `failed`, `error`, timestamps
- **`VersionOutput`** (`quality_assurance.version_output`): actual output for a given input. Session-scoped via `qa_session_id` (async runs) or keyed by `(input_id, graph_runner_id)` for legacy sync runs

## LLM Judges

**Table**: `quality_assurance.llm_judges`

Fields: `organization_id`, `name`, `description`, `evaluation_type`, `llm_model_reference` (default `openai:gpt-5-mini`), `prompt_template`, `temperature`.

Judges can be associated with multiple projects via the `llm_judge_project_associations` table (`judge_id`, `project_id`).

### CRUD Endpoints (Organization-scoped)

- `GET /organizations/{organization_id}/qa/llm-judges` — list judges
- `POST /organizations/{organization_id}/qa/llm-judges` — create judge
- `PATCH /organizations/{organization_id}/qa/llm-judges/{judge_id}` — update
- `DELETE /organizations/{organization_id}/qa/llm-judges` — delete judges
- `PUT /organizations/{organization_id}/qa/llm-judges/{judge_id}/projects` — set project associations

### Evaluation Types

| Type | Mechanism | Output |
|---|---|---|
| `boolean` | LLM evaluates and returns true/false | Pass/fail |
| `score` | LLM evaluates and returns a numeric score | 0-10 score |
| `free_text` | LLM provides free-form evaluation | Text feedback |
| `json_equality` | Deterministic JSON comparison | Exact match result |

LLM-based types use `CompletionService.constrained_complete_with_pydantic_async()` with prompt template variables: `{input}`, `{groundtruth}`, `{output}`.

The `json_equality` type uses deterministic comparison via `run_deterministic_evaluation_service`.

### Running Evaluations

`POST /projects/{project_id}/qa/llm-judges/{judge_id}/evaluations/run`

Evaluates a judge against version outputs, storing results as `JudgeEvaluation` records.

## Import/Export (Organization-scoped)

- **Export**: `POST /organizations/{organization_id}/qa/datasets/{dataset_id}/export?graph_runner_id=...` → CSV
- **Import**: `POST /organizations/{organization_id}/qa/datasets/{dataset_id}/import` → CSV upload

## From Trace to QA

`POST /organizations/{organization_id}/qa/datasets/{dataset_id}/entries/from-history` — converts a trace execution into a QA dataset entry (capturing input and actual output as groundtruth).

## Key Files

- `routers/quality_assurance_router.py` — dataset + entry CRUD, run (sync + async), import/export. Thin transport layer: delegates all business logic and DB writes to the QA service.
- `routers/qa_stream_router.py` — WebSocket endpoint for async QA session streaming (auth only; delegates to service)
- `routers/llm_judges_router.py` — judge CRUD, defaults
- `routers/qa_evaluation_router.py` — evaluation run, results
- `services/qa/quality_assurance_service.py` — dataset CRUD, project association with column mappings, QA session lifecycle, dataset validation, run orchestration
- `services/qa/qa_stream_service.py` — session replay, Redis subscription, and event streaming logic for the QA WebSocket
- `services/qa/qa_evaluation_service.py` — LLM evaluation logic
- `workers/qa_queue_worker.py` — `QAQueueWorker` subclass of `BaseQueueWorker` for async QA jobs
- `workers/base_queue_worker.py` — shared BLPOP worker infrastructure (heartbeat, orphan recovery, drain)
- `utils/redis_client.py` → `push_qa_task()` — enqueues a QA job onto the Redis queue
- `schemas/llm_judges_schema.py` — Pydantic schemas
