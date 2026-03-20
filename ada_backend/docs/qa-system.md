# Quality Assurance System

The QA system enables testing workflows against datasets of input/groundtruth pairs, with LLM-based evaluation judges.

## Datasets

Datasets belong to a project and contain input/groundtruth entries. Each dataset can have custom metadata columns.

- **`DatasetProject`** (`quality_assurance.dataset_project`): `project_id`, `name`
- **`InputGroundtruth`** (`quality_assurance.input_groundtruth`): `dataset_id`, `input_data`, `groundtruth`, `position`, custom column values
- **`QADatasetMetadata`** (`quality_assurance.qa_dataset_metadata`): custom column definitions per dataset

## QA Run Process

`POST /projects/{project_id}/qa/datasets/{dataset_id}/run`

1. Select specific entries or all entries in the dataset
2. Execute the project's graph version against each entry's input
3. Store results as `VersionOutput` records (keyed by input + graph_runner_id)

- **`VersionOutput`** (`quality_assurance.version_output`): actual output for a given (input, graph_runner_id) pair

## LLM Judges

**Table**: `quality_assurance.llm_judges`

Fields: `project_id`, `name`, `description`, `evaluation_type`, `llm_model_reference` (default `openai:gpt-5-mini`), `prompt_template`, `temperature`.

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

## Import/Export

- **Export**: `GET .../datasets/{dataset_id}/export?graph_runner_id=...` → CSV
- **Import**: `POST .../datasets/{dataset_id}/import` → CSV upload

## From Trace to QA

`POST .../datasets/{dataset_id}/entries/from-history` — converts a trace execution into a QA dataset entry (capturing input and actual output as groundtruth).

## Key Files

- `routers/quality_assurance_router.py` — dataset + entry CRUD, run, import/export
- `routers/llm_judges_router.py` — judge CRUD, defaults
- `routers/qa_evaluation_router.py` — evaluation run, results
- `services/qa/qa_evaluation_service.py` — LLM evaluation logic
- `schemas/llm_judges_schema.py` — Pydantic schemas
