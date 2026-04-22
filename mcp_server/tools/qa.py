"""Quality assurance tools (datasets, entries, judges, evaluations)."""

import csv
import io
import json
from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field

from mcp_server.client import api
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

_P_ORG = Param("organization_id", UUID, description="The organization ID (from select_organization).")
_P_PROJECT = Param("project_id", UUID, description="The project ID (from list_projects or get_project_overview).")
_P_DATASET = Param("dataset_id", UUID, description="The dataset ID (from list_datasets or create_dataset).")
_P_JUDGE = Param("judge_id", UUID, description="The judge ID (from list_judges or create_judge).")

_ORG_QA = "/organizations/{organization_id}/qa"
_DS = f"{_ORG_QA}/datasets"
_DS_ITEM = f"{_DS}/{{dataset_id}}"
_ENTRIES = f"{_DS_ITEM}/entries"
_CUSTOM_COLS = f"{_DS_ITEM}/custom-columns"
_JUDGES = f"{_ORG_QA}/llm-judges"
_JUDGE_ITEM = f"{_JUDGES}/{{judge_id}}"

_PROJ_QA = "/projects/{project_id}/qa"

SPECS: list[ToolSpec] = [
    # --- Datasets (org-scoped) ---
    ToolSpec(
        name="list_datasets",
        description="List QA datasets for an organization.",
        method="get",
        path=_DS,
        path_params=(_P_ORG,),
        return_annotation=list,
    ),
    ToolSpec(
        name="create_dataset",
        description=(
            "Create a new QA dataset.\n\n"
            "Duplicate names are allowed — call `list_datasets` first to check if the "
            "dataset already exists and reuse its ID instead of creating a new one."
        ),
        method="post",
        path=_DS,
        path_params=(_P_ORG,),
        body_param=Param(
            "dataset_data", dict,
            description="Dataset configuration. Required fields: datasets_name (list[str]).",
        ),
    ),
    ToolSpec(
        name="update_dataset",
        description="Rename a QA dataset.",
        method="patch",
        path=_DS_ITEM,
        path_params=(_P_ORG, _P_DATASET),
        query_params=(Param("dataset_name", str, description="New name for the dataset."),),
    ),
    ToolSpec(
        name="delete_datasets",
        description="Destructive. Delete one or more QA datasets.",
        method="delete",
        path=_DS,
        path_params=(_P_ORG,),
        body_fields=(Param("dataset_ids", list, description="List of dataset IDs to delete."),),
    ),
    ToolSpec(
        name="set_dataset_projects",
        description="Set which projects a dataset is associated with (replaces existing associations).",
        method="put",
        path=f"{_DS_ITEM}/projects",
        path_params=(_P_ORG, _P_DATASET),
        body_fields=(Param("project_ids", list, description="List of project IDs to associate."),),
    ),
    # --- Entries (org-scoped) ---
    ToolSpec(
        name="list_entries",
        description=(
            "List entries in a QA dataset (paginated).\n\n"
            "Returns `{pagination: {page, size, total_items, total_pages}, "
            "inputs_groundtruths: [...]}`. Each entry has `id`, `input`, "
            "`groundtruth`, `position`, `custom_columns`, `created_at`, `updated_at`.\n\n"
            "Truncation caveat: responses over 50KB are trimmed (`_truncated: true`). "
            "For datasets with large inputs or many custom columns, use a smaller "
            "`page_size` (e.g. 10–20) to avoid truncation. For full dataset export, "
            "prefer `export_dataset_csv`."
        ),
        method="get",
        path=_ENTRIES,
        path_params=(_P_ORG, _P_DATASET),
        query_params=(
            Param("page", int, default=1, description="Page number (1-based)."),
            Param("page_size", int, default=100, description="Items per page (max 1000)."),
        ),
    ),
    ToolSpec(
        name="create_entries",
        description=(
            "Add entries to a QA dataset.\n\n"
            "Each entry requires `input` (dict, e.g. {\"role\": \"user\", \"content\": \"hello\"}) "
            "and optionally `groundtruth` (str), `position` (int >= 1), "
            "and `custom_columns` (dict).\n\n"
            "Custom columns: keys MUST be the column UUID (not the display name). "
            "Call `list_custom_columns` first to get the `column_id` → `column_name` mapping. "
            "Example: `{\"1b39fa0b-...\": \"my value\"}`, NOT `{\"my column\": \"my value\"}`."
        ),
        method="post",
        path=_ENTRIES,
        path_params=(_P_ORG, _P_DATASET),
        body_fields=(Param(
            "inputs_groundtruths", list,
            description="List of input/groundtruth objects.",
        ),),
    ),
    ToolSpec(
        name="update_entries",
        description=(
            "Update entries in a QA dataset.\n\n"
            "Each object requires `id` (UUID). Optional fields: `input` (dict), "
            "`groundtruth` (str), `custom_columns` (dict).\n\n"
            "Custom columns use merge semantics: only specified keys are updated. "
            "Pass `null` as a value to remove a key. Keys MUST be column UUIDs — "
            "call `list_custom_columns` to get the mapping. "
            "Warning: changing `input` clears existing outputs and evaluations for that entry."
        ),
        method="patch",
        path=_ENTRIES,
        path_params=(_P_ORG, _P_DATASET),
        body_fields=(Param(
            "inputs_groundtruths", list,
            description="List of input/groundtruth objects with their IDs and updated fields.",
        ),),
    ),
    ToolSpec(
        name="delete_entries",
        description="Destructive. Delete entries from a QA dataset.",
        method="delete",
        path=_ENTRIES,
        path_params=(_P_ORG, _P_DATASET),
        body_fields=(
            Param(
                "input_groundtruth_ids", list,
                description="List of input/groundtruth pair IDs to delete (as returned by list_entries).",
            ),
        ),
    ),
    ToolSpec(
        name="save_trace_to_qa",
        description="Save a trace execution as a QA dataset entry.",
        method="post",
        path=f"{_ENTRIES}/from-history",
        path_params=(_P_ORG, _P_DATASET),
        query_params=(Param("trace_id", UUID, description="The trace ID to save as a QA entry (from list_traces)."),),
    ),
    # --- Custom Columns (org-scoped) ---
    ToolSpec(
        name="list_custom_columns",
        description=(
            "List custom column definitions for a QA dataset.\n\n"
            "Returns the column schema: each column has `column_id` (UUID — the key used "
            "in entry `custom_columns` dicts), `column_name` (human-readable label), "
            "and `column_display_position` (ordering).\n\n"
            "Call this before `create_entries` or `update_entries` when working with "
            "custom columns — you need the `column_id` UUIDs, not the display names."
        ),
        method="get",
        path=_CUSTOM_COLS,
        path_params=(_P_ORG, _P_DATASET),
        return_annotation=list,
    ),
    # --- QA Runs (project-scoped) ---
    ToolSpec(
        name="run_qa",
        description=(
            "Run a QA evaluation on a dataset against a graph version.\n\n"
            "Frontend safety rule: if a test input changes, treat any existing "
            "`output`, `evaluations`, and `version_output_id` as stale."
        ),
        method="post",
        path=f"{_PROJ_QA}/datasets/{{dataset_id}}/run",
        path_params=(_P_PROJECT, _P_DATASET),
        body_param=Param(
            "run_config", dict,
            description=(
                "Run configuration. Required: graph_runner_id (str). "
                "Plus either input_ids (list[str]) or run_all (bool)."
            ),
        ),
    ),
    # --- Judges (org-scoped) ---
    ToolSpec(
        name="list_judges",
        description="List LLM judges for an organization.",
        method="get",
        path=_JUDGES,
        path_params=(_P_ORG,),
        return_annotation=list,
    ),
    ToolSpec(
        name="get_judge_defaults",
        description="Get default judge configurations (evaluation types, prompts).",
        method="get",
        path="/qa/llm-judges/defaults",
    ),
    ToolSpec(
        name="create_judge",
        description=(
            "Create a new LLM judge.\n\n"
            "Use get_judge_defaults to see available types and prompt templates."
        ),
        method="post",
        path=_JUDGES,
        path_params=(_P_ORG,),
        body_param=Param(
            "judge_data", dict,
            description=(
                "Judge configuration. Required: name (str), "
                "evaluation_type ('boolean', 'score', 'free_text', or 'json_equality'), "
                "prompt_template (str), llm_model_reference (str, e.g. 'openai:gpt-4o'). "
                "Optional: description (str), temperature (float, default 1.0)."
            ),
        ),
    ),
    ToolSpec(
        name="update_judge",
        description="Update an LLM judge.",
        method="patch",
        path=_JUDGE_ITEM,
        path_params=(_P_ORG, _P_JUDGE),
        body_param=Param("judge_data", dict, description="Updated judge fields."),
    ),
    ToolSpec(
        name="delete_judges",
        description="Destructive. Delete one or more LLM judges.",
        method="delete",
        path=_JUDGES,
        path_params=(_P_ORG,),
        body_param=Param("judge_ids", list, description="List of judge IDs to delete."),
    ),
    ToolSpec(
        name="set_judge_projects",
        description="Set which projects a judge is associated with (replaces existing associations).",
        method="put",
        path=f"{_JUDGE_ITEM}/projects",
        path_params=(_P_ORG, _P_JUDGE),
        body_fields=(Param("project_ids", list, description="List of project IDs to associate."),),
    ),
    # --- Evaluations (project-scoped) ---
    ToolSpec(
        name="run_evaluation",
        description=(
            "Run an evaluation using an LLM judge on a single version output.\n\n"
            "The MCP tool is judge-centric: call it once per judge. Use "
            "`get_evaluations(project_id, version_output_id)` to inspect the scores "
            "written for each output afterward."
        ),
        method="post",
        path=f"{_PROJ_QA}/llm-judges/{{judge_id}}/evaluations/run",
        path_params=(_P_PROJECT, _P_JUDGE),
        body_fields=(
            Param(
                "version_output_id",
                UUID,
                description="The version output ID to evaluate (from run_qa results).",
            ),
        ),
    ),
    ToolSpec(
        name="get_evaluations",
        description="Get evaluation results for a version output.",
        method="get",
        path=f"{_PROJ_QA}/version-outputs/{{version_output_id}}/evaluations",
        path_params=(
            _P_PROJECT,
            Param("version_output_id", UUID, description="The version output ID (from run_qa results)."),
        ),
        return_annotation=list,
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)

    @mcp.tool()
    async def export_dataset_csv(
        organization_id: Annotated[UUID, Field(description="The organization ID (from select_organization).")],
        dataset_id: Annotated[UUID, Field(description="The dataset ID (from list_datasets or create_dataset).")],
    ) -> str:
        """Export all entries in a QA dataset as CSV text.

        Returns CSV with columns: position, input (JSON string), expected_output,
        plus custom columns (using display names as headers). Compatible with
        `import_dataset_csv` for round-trip workflows (sort, filter, migrate).
        """
        jwt, _ = _get_auth()

        columns = await api.get(
            f"/organizations/{organization_id}/qa/datasets/{dataset_id}/custom-columns",
            jwt, trim=False,
        )
        sorted_cols = sorted(columns, key=lambda c: c.get("column_display_position", 0))

        all_entries: list[dict] = []
        page = 1
        while True:
            resp = await api.get(
                f"/organizations/{organization_id}/qa/datasets/{dataset_id}/entries",
                jwt, page=page, page_size=100, trim=False,
            )
            all_entries.extend(resp.get("inputs_groundtruths", []))
            if page >= resp.get("pagination", {}).get("total_pages", 1):
                break
            page += 1

        headers = ["position", "input", "expected_output"]
        headers.extend(c["column_name"] for c in sorted_cols)

        if not all_entries:
            output = io.StringIO()
            csv.writer(output).writerow(headers)
            return output.getvalue()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)

        for entry in sorted(all_entries, key=lambda e: e.get("position") or 0):
            custom = entry.get("custom_columns") or {}
            row = [
                entry.get("position", ""),
                json.dumps(entry.get("input", {})),
                entry.get("groundtruth", ""),
            ]
            row.extend(custom.get(c["column_id"], "") for c in sorted_cols)
            writer.writerow(row)

        return output.getvalue()

    @mcp.tool()
    async def import_dataset_csv(
        organization_id: Annotated[UUID, Field(description="The organization ID (from select_organization).")],
        dataset_id: Annotated[UUID, Field(description="The dataset ID (from list_datasets or create_dataset).")],
        csv_content: Annotated[str, Field(description="The full CSV text to import.")],
    ) -> dict:
        """Import entries into a QA dataset from CSV text.

        Required CSV columns: `input` (valid JSON string), `expected_output`.
        Optional: `position` (int >= 1). Any other column headers are treated as
        custom columns — new ones are auto-created in the dataset.

        If the dataset already has custom columns, the CSV must include ALL of them
        (the backend rejects CSVs missing existing custom columns).

        This appends entries. To replace all entries, delete existing ones first
        with `delete_entries`, then import.
        """
        jwt, _ = _get_auth()

        return await api.post_file(
            f"/organizations/{organization_id}/qa/datasets/{dataset_id}/import",
            jwt,
            file_content=csv_content.encode("utf-8"),
            filename="import.csv",
        )
