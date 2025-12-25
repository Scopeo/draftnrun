"""
Pytest configuration and result reporting for external API call tests.
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from engine.trace.span_context import set_tracing_span
from .capability_matrix import (
    CAPABILITY_MATRIX,
    get_all_providers,
    get_capability_display_name,
)


# Store test results: capability_key -> provider -> model -> status
_RESULT_STORE: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
_ISSUES: list[dict[str, Any]] = []


@pytest.fixture(autouse=True)
def _setup_tracing_context() -> None:
    set_tracing_span(
        project_id="test-project",
        organization_id="test-org",
        organization_llm_providers=["openai", "mistral", "google", "cerebras", "anthropic"],
        conversation_id="test-conversation",
    )


def _ensure_seeded_results() -> None:
    if _RESULT_STORE:
        return

    for provider, capabilities_by_modality in CAPABILITY_MATRIX.items():
        for modality, capabilities in capabilities_by_modality.items():
            for capability, models in capabilities.items():
                capability_key = f"{modality}.{capability}"
                if not models:
                    # Empty list means not supported
                    _RESULT_STORE[capability_key][provider]["N/A"] = "N/A"
                else:
                    # Mark as pending for each model
                    for model in models:
                        _RESULT_STORE[capability_key][provider][model] = "PENDING"


def _infer_capability_from_nodeid(nodeid: str) -> str | None:
    """
    Infer the capability key (modality.capability) from the test nodeid.

    Examples:
        test_text_modality.py::TestTextModality::TestComplete::test_basic_completion
            -> "text.complete"
        test_vision_modality.py::TestVisionModality::TestComplete::test_basic_image_description
            -> "vision.complete"
    """
    if "::" not in nodeid:
        return None

    parts = nodeid.split("::")
    if len(parts) < 2:
        return None

    file_part = parts[0]

    modality = None
    if "test_text_modality" in file_part:
        modality = "text"
    elif "test_vision_modality" in file_part:
        modality = "vision"
    elif "test_specialized_services" in file_part:
        modality = "specialized"

    if not modality:
        return None

    test_func = parts[-1]
    if "[" in test_func:
        test_func = test_func.split("[", 1)[0]

    capability_mapping = {
        "test_basic_completion": "complete",
        "test_structured_output_pydantic": "complete_structured_pydantic",
        "test_structured_output_json_schema": "complete_structured_json_schema",
        "test_basic_function_call": "function_call",
        "test_function_call_with_structured_output": "function_call_structured",
        "test_function_call_with_system_message": "function_call_with_system",
        "test_function_call_with_empty_tools": "function_call_empty_tools",
        "test_function_call_with_tool_choice_none": "function_call_tool_choice_none",
        "test_function_call_structured_with_tool_choice_none": "function_call_tool_choice_none",
        "test_multi_turn_function_calling_with_tool_responses": "function_call_multi_turn",
        "test_function_call_with_both_regular_and_structured_tools": "function_call_both_tools_and_structured",
        "test_basic_image_description": "complete",
        "test_image_description_with_structured_output": "complete_structured",
        "test_vision_function_call_with_structured_output": "function_call_structured",
        "test_embedding_service": "embedding",
        "test_embedding_service_async_returns_objects_with_embedding_attribute": "embedding_async",
        "test_ocr_service": "ocr",
        "test_web_search_service": "web_search",
    }

    capability = capability_mapping.get(test_func)
    if capability:
        return f"{modality}.{capability}"

    return None


def _infer_provider_and_model_from_nodeid(nodeid: str) -> tuple[str | None, str | None]:
    if "[" not in nodeid or not nodeid.endswith("]"):
        return None, None

    param_str = nodeid.rsplit("[", 1)[-1].rstrip("]")

    # Pytest sanitizes '/' to '-' in test IDs, so we split on '-' instead
    # Split on first '-' only since model names also contain '-'
    if "-" in param_str:
        parts = param_str.split("-", 1)
        return parts[0], parts[1]

    return None, None


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when not in {"setup", "call"}:
        return

    _ensure_seeded_results()

    capability_key = _infer_capability_from_nodeid(report.nodeid)
    provider, model = _infer_provider_and_model_from_nodeid(report.nodeid)

    if not capability_key or not provider or not model:
        return

    existing = _RESULT_STORE.get(capability_key, {}).get(provider, {}).get(model)
    is_applicable = existing is not None and existing != "N/A"

    if report.when == "call" and report.outcome == "passed":
        _RESULT_STORE[capability_key][provider][model] = "PASS"
        return

    if report.when == "call" and report.outcome == "failed":
        _RESULT_STORE[capability_key][provider][model] = "FAIL"
        exc_msg = None
        if hasattr(report, "longrepr") and hasattr(report.longrepr, "reprcrash"):
            exc_msg = getattr(report.longrepr.reprcrash, "message", None)
        if exc_msg:
            exc_msg = str(exc_msg)[:500]
        _ISSUES.append(
            {
                "nodeid": report.nodeid,
                "capability": capability_key,
                "provider": provider,
                "model": model,
                "reason": exc_msg,
            }
        )
        return

    if report.outcome == "skipped" and is_applicable:
        _RESULT_STORE[capability_key][provider][model] = "FAIL"
        reason = None
        longrepr = getattr(report, "longrepr", None)
        if isinstance(longrepr, tuple) and len(longrepr) == 3:
            reason = longrepr[2]
        if reason is None and longrepr is not None:
            reason = str(longrepr)
        if reason:
            reason = str(reason)[:500]
        _ISSUES.append(
            {
                "nodeid": report.nodeid,
                "capability": capability_key,
                "provider": provider,
                "model": model,
                "reason": reason,
            }
        )
        return


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    _ensure_seeded_results()

    has_results = False
    for capability_results in _RESULT_STORE.values():
        for provider_results in capability_results.values():
            for status in provider_results.values():
                if status not in ("N/A", "PENDING"):
                    has_results = True
                    break
            if has_results:
                break
        if has_results:
            break

    if not has_results:
        return

    report_path_env = os.getenv("EXTERNAL_API_CALLS_REPORT_PATH")
    if report_path_env:
        report_path = Path(report_path_env)
    else:
        report_path = Path("tests/external_api_calls/external_api_calls_matrix.md")

    providers = get_all_providers()
    capabilities_list = sorted(_RESULT_STORE.keys())

    lines: list[str] = []
    lines.append("## External LLM API calls coverage matrix")
    lines.append("")

    header_cells = ["Capability"] + providers
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

    for capability_key in capabilities_list:
        modality, capability = capability_key.split(".", 1)
        display_name = get_capability_display_name(modality, capability)
        row = [display_name]

        for provider in providers:
            provider_results = _RESULT_STORE[capability_key].get(provider, {})

            if not provider_results or "N/A" in provider_results:
                row.append("N/A")
            else:
                model_statuses = []
                for model, status in provider_results.items():
                    if status == "PENDING":
                        status = "FAIL"
                        _ISSUES.append(
                            {
                                "nodeid": None,
                                "capability": capability_key,
                                "provider": provider,
                                "model": model,
                                "reason": "Test was expected but no result was recorded.",
                            }
                        )

                    if status == "PASS":
                        model_statuses.append(f"✅ {model}")
                    else:
                        model_statuses.append(f"❌ {model}")

                row.append("<br>".join(model_statuses) if model_statuses else "N/A")

        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("Legend:")
    lines.append("- `✅ model-name` = Test passed for this model")
    lines.append("- `❌ model-name` = Test failed for this model")
    lines.append("- `N/A` = Provider doesn't support this capability")

    if _ISSUES:
        lines.append("")
        lines.append("### Failures (including skips)")
        lines.append("")
        for issue in _ISSUES:
            capability = issue.get("capability", "unknown")
            provider = issue.get("provider", "unknown")
            model = issue.get("model", "unknown")
            nodeid = issue.get("nodeid")
            reason = issue.get("reason", "No reason provided")

            if nodeid:
                lines.append(f"- `{provider}/{model}` / `{capability}`: `{nodeid}` -> {reason}")
            else:
                lines.append(f"- `{provider}/{model}` / `{capability}` -> {reason}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    report_path_env = os.getenv("EXTERNAL_API_CALLS_REPORT_PATH")
    if report_path_env:
        report_path = Path(report_path_env)
    else:
        report_path = Path("tests/external_api_calls/external_api_calls_matrix.md")

    if report_path.exists():
        terminalreporter.write_sep("=", "External LLM API calls report")
        terminalreporter.write_line(f"Markdown report written to: {report_path}")
