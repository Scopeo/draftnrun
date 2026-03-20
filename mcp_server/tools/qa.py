"""Quality assurance tools (datasets, entries, judges, evaluations)."""

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

_P_PROJECT = Param("project_id", str, description="The project ID.")
_P_DATASET = Param("dataset_id", str, description="The dataset ID.")
_P_JUDGE = Param("judge_id", str, description="The judge ID.")

_QA = "/projects/{project_id}/qa"
_DS = f"{_QA}/datasets"
_DS_ITEM = f"{_DS}/{{dataset_id}}"
_ENTRIES = f"{_DS_ITEM}/entries"
_JUDGES = f"{_QA}/llm-judges"
_JUDGE_ITEM = f"{_JUDGES}/{{judge_id}}"

SPECS: list[ToolSpec] = [
    # --- Datasets ---
    ToolSpec(
        name="list_datasets",
        description="List QA datasets for a project.",
        method="get",
        path=_DS,
        path_params=(_P_PROJECT,),
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
        path_params=(_P_PROJECT,),
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
        path_params=(_P_PROJECT, _P_DATASET),
        query_params=(Param("dataset_name", str, description="New name for the dataset."),),
    ),
    ToolSpec(
        name="delete_datasets",
        description="Delete one or more QA datasets.",
        method="delete",
        path=_DS,
        path_params=(_P_PROJECT,),
        body_fields=(Param("dataset_ids", list, description="List of dataset IDs to delete."),),
    ),
    # --- Entries ---
    ToolSpec(
        name="list_entries",
        description=(
            "List entries in a QA dataset (paginated).\n\n"
            "Returns `{pagination: {page, size, total_items, total_pages}, "
            "inputs_groundtruths: [...]}`. Each entry has `id`, `input`, "
            "`groundtruth`, `position`, `custom_columns`, `created_at`, `updated_at`."
        ),
        method="get",
        path=_ENTRIES,
        path_params=(_P_PROJECT, _P_DATASET),
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
            "and `custom_columns` (dict)."
        ),
        method="post",
        path=_ENTRIES,
        path_params=(_P_PROJECT, _P_DATASET),
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
            "`groundtruth` (str), `custom_columns` (dict)."
        ),
        method="patch",
        path=_ENTRIES,
        path_params=(_P_PROJECT, _P_DATASET),
        body_fields=(Param(
            "inputs_groundtruths", list,
            description="List of input/groundtruth objects with their IDs and updated fields.",
        ),),
    ),
    ToolSpec(
        name="delete_entries",
        description="Delete entries from a QA dataset.",
        method="delete",
        path=_ENTRIES,
        path_params=(_P_PROJECT, _P_DATASET),
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
        path_params=(_P_PROJECT, _P_DATASET),
        query_params=(Param("trace_id", str, description="The trace ID to save as a QA entry."),),
    ),
    ToolSpec(
        name="run_qa",
        description=(
            "Run a QA evaluation on a dataset against a graph version.\n\n"
            "Frontend safety rule: if a test input changes, treat any existing "
            "`output`, `evaluations`, and `version_output_id` as stale."
        ),
        method="post",
        path=f"{_DS_ITEM}/run",
        path_params=(_P_PROJECT, _P_DATASET),
        body_param=Param(
            "run_config", dict,
            description=(
                "Run configuration. Required: graph_runner_id (str). "
                "Plus either input_ids (list[str]) or run_all (bool)."
            ),
        ),
    ),
    # --- Judges ---
    ToolSpec(
        name="list_judges",
        description="List LLM judges for a project.",
        method="get",
        path=_JUDGES,
        path_params=(_P_PROJECT,),
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
        path_params=(_P_PROJECT,),
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
        path_params=(_P_PROJECT, _P_JUDGE),
        body_param=Param("judge_data", dict, description="Updated judge fields."),
    ),
    ToolSpec(
        name="delete_judges",
        description="Delete one or more LLM judges.",
        method="delete",
        path=_JUDGES,
        path_params=(_P_PROJECT,),
        body_param=Param("judge_ids", list, description="List of judge IDs to delete."),
    ),
    ToolSpec(
        name="run_evaluation",
        description=(
            "Run an evaluation using an LLM judge on a single version output.\n\n"
            "The MCP tool is judge-centric: call it once per judge. Use "
            "`get_evaluations(project_id, version_output_id)` to inspect the scores "
            "written for each output afterward."
        ),
        method="post",
        path=f"{_JUDGE_ITEM}/evaluations/run",
        path_params=(_P_PROJECT, _P_JUDGE),
        body_fields=(Param("version_output_id", str, description="The version output ID to evaluate."),),
    ),
    ToolSpec(
        name="get_evaluations",
        description="Get evaluation results for a version output.",
        method="get",
        path=f"{_QA}/version-outputs/{{version_output_id}}/evaluations",
        path_params=(
            _P_PROJECT,
            Param("version_output_id", str, description="The version output ID."),
        ),
        return_annotation=list,
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
