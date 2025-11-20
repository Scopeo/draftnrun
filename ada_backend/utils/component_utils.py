"""Utility functions for component-related operations."""

from sqlalchemy.orm import Session

from ada_backend.services.llm_models_service import get_llm_models_by_capability_select_options_service


def get_ui_component_properties_with_llm_options(
    session: Session,
    model_capabilities: list | None,
    ui_component_properties: dict | None,
) -> dict | None:
    """Get UI component properties with LLM model options added."""

    return {
        **(ui_component_properties or {}),
        "options": get_llm_models_by_capability_select_options_service(
            session,
            model_capabilities,
        ),
    }
