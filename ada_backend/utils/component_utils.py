"""Utility functions for component-related operations."""

from sqlalchemy.orm import Session

from ada_backend.services.llm_models_service import get_llm_models_by_capability_select_options_service


def get_ui_component_properties_with_llm_options(
    session: Session,
    model_capabilities: list | None,
    ui_component_properties: dict | None,
    llm_options_cache: dict[frozenset, list] | None = None,
) -> dict | None:
    """Get UI component properties with LLM model options added.

    Pass ``llm_options_cache`` (a dict keyed by frozenset of capability strings)
    to avoid repeated DB queries when multiple parameters share the same capability set.
    """
    cache_key = frozenset(model_capabilities or [])
    if llm_options_cache is not None and cache_key in llm_options_cache:
        options = llm_options_cache[cache_key]
    else:
        options = get_llm_models_by_capability_select_options_service(session, model_capabilities)
        if llm_options_cache is not None:
            llm_options_cache[cache_key] = options
    return {**(ui_component_properties or {}), "options": options}
