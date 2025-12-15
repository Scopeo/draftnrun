import logging
from collections import defaultdict, deque
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.component_repository import (
    get_component_instances_for_graph_runner,
    get_output_ports_for_component_version,
)
from ada_backend.repositories.edge_repository import get_edges
from ada_backend.schemas.pipeline.field_expression_schema import (
    FieldExpressionAutocompleteRequest,
    FieldExpressionAutocompleteResponse,
    FieldExpressionSuggestion,
    FieldExpressionSuggestionDetail,
    FieldExpressionSuggestionKind,
)
from ada_backend.services.graph.graph_validation_utils import validate_graph_runner_belongs_to_project
from engine.field_expressions.autocomplete import FieldExpressionCursorContext, get_cursor_context

LOGGER = logging.getLogger(__name__)


def autocomplete_field_expression(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
    request: FieldExpressionAutocompleteRequest,
) -> FieldExpressionAutocompleteResponse:
    validate_graph_runner_belongs_to_project(session, graph_runner_id, project_id)

    cursor_context = get_cursor_context(request.expression_text or "", request.cursor_offset)
    if not cursor_context:
        return FieldExpressionAutocompleteResponse(suggestions=[])

    instances = get_component_instances_for_graph_runner(session, graph_runner_id)
    if not instances:
        return FieldExpressionAutocompleteResponse(suggestions=[])

    upstream_instance_ids = _get_upstream_instance_ids(session, graph_runner_id, request.target_instance_id)
    if not upstream_instance_ids:
        return FieldExpressionAutocompleteResponse(suggestions=[])

    eligible_instances = [instance for instance in instances if instance.id in upstream_instance_ids]
    if not eligible_instances:
        return FieldExpressionAutocompleteResponse(suggestions=[])

    suggestions: list[FieldExpressionSuggestion]

    if cursor_context.phase == FieldExpressionSuggestionKind.INSTANCE:
        suggestions = _build_instance_suggestions(eligible_instances, cursor_context.instance_prefix)
    elif cursor_context.phase == FieldExpressionSuggestionKind.PORT:
        suggestions = _build_port_suggestions(session, eligible_instances, cursor_context)
    else:
        # TODO: Offer structured key suggestions once we expose metadata about port output structure
        # (e.g. known dict keys) from the engine.
        suggestions = []

    LOGGER.debug(
        "Field expression autocomplete: phase=%s count=%d",
        cursor_context.phase.value,
        len(suggestions),
    )
    return FieldExpressionAutocompleteResponse(suggestions=suggestions)


def _build_instance_suggestions(
    instances: Iterable[db.ComponentInstance],
    typed_prefix: str | None,
) -> list[FieldExpressionSuggestion]:
    prefix = (typed_prefix or "").lower()
    suggestions: list[FieldExpressionSuggestion] = []
    for instance in instances:
        instance_id_str = str(instance.id)
        if prefix and not instance_id_str.lower().startswith(prefix):
            continue
        insert_text = _missing_suffix(instance_id_str, typed_prefix or "")
        suggestions.append(
            FieldExpressionSuggestion(
                label=instance.name or instance_id_str,
                insert_text=insert_text,
                kind=FieldExpressionSuggestionKind.INSTANCE,
                detail=FieldExpressionSuggestionDetail(
                    instance_id=instance.id,
                    instance_name=instance.name,
                ),
            )
        )

    suggestions.sort(
        key=lambda s: (
            s.detail.instance_name or "",
            str(s.detail.instance_id) if s.detail.instance_id else "",
        )
    )
    return suggestions


def _build_port_suggestions(
    session: Session,
    instances: Iterable[db.ComponentInstance],
    cursor_context: FieldExpressionCursorContext,
) -> list[FieldExpressionSuggestion]:
    typed_instance = (cursor_context.instance_prefix or "").strip()
    if not typed_instance:
        return []
    try:
        instance_uuid = UUID(typed_instance)
    except ValueError:
        return []

    instance_map = {inst.id: inst for inst in instances}
    if instance_uuid not in instance_map:
        return []

    instance = instance_map[instance_uuid]
    ports = get_output_ports_for_component_version(session, instance.component_version_id)

    prefix = (cursor_context.port_prefix or "").lower()
    suggestions: list[FieldExpressionSuggestion] = []
    for port in ports:
        port_name = port.name or ""
        if prefix and not port_name.lower().startswith(prefix):
            continue
        insert_text = _missing_suffix(port_name, cursor_context.port_prefix or "")
        suggestions.append(
            FieldExpressionSuggestion(
                label=f"{instance.name or instance.id}.{port_name}",
                insert_text=insert_text,
                kind=FieldExpressionSuggestionKind.PORT,
                detail=FieldExpressionSuggestionDetail(
                    instance_id=instance.id,
                    instance_name=instance.name,
                    port_name=port_name,
                    port_type=port.port_type,
                ),
            )
        )
    return suggestions


def _missing_suffix(full_value: str, typed_prefix: str) -> str:
    if not typed_prefix:
        return full_value
    prefix_len = len(typed_prefix)
    if prefix_len >= len(full_value):
        return ""
    return full_value[prefix_len:]


def _get_upstream_instance_ids(session: Session, graph_runner_id: UUID, target_instance_id: UUID) -> set[UUID]:
    """Return all component instance ids that have a path to the target instance."""
    edges = get_edges(session, graph_runner_id)
    predecessors: dict[UUID, set[UUID]] = defaultdict(set)
    for edge in edges:
        if edge.source_node_id and edge.target_node_id:
            predecessors[edge.target_node_id].add(edge.source_node_id)

    visited: set[UUID] = set()
    queue: deque[UUID] = deque(predecessors.get(target_instance_id, []))

    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        for parent in predecessors.get(node_id, []):
            queue.append(parent)

    return visited
