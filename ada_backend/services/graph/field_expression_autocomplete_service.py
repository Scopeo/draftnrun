import logging
from collections import defaultdict, deque
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.component_repository import get_output_ports_for_component_version
from ada_backend.repositories.edge_repository import get_edges
from ada_backend.repositories.graph_runner_repository import (
    get_component_instances_for_graph_runner,
    is_start_node,
)
from ada_backend.schemas.pipeline.field_expression_schema import (
    FieldExpressionAutocompleteRequest,
    FieldExpressionAutocompleteResponse,
    FieldExpressionSuggestion,
    SuggestionKind,
)
from ada_backend.services.graph.graph_validation_utils import validate_graph_runner_belongs_to_project
from ada_backend.services.graph.playground_utils import extract_playground_schema_from_component
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance

LOGGER = logging.getLogger(__name__)


def autocomplete_field_expression(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
    request: FieldExpressionAutocompleteRequest,
) -> FieldExpressionAutocompleteResponse:
    validate_graph_runner_belongs_to_project(session, graph_runner_id, project_id)

    query = request.query or ""
    phase = _get_phase_from_query(query)

    instances = get_component_instances_for_graph_runner(session, graph_runner_id)
    if not instances:
        LOGGER.debug("No instances found for graph_runner_id=%s", graph_runner_id)
        return FieldExpressionAutocompleteResponse(suggestions=[])

    upstream_instance_ids = _get_upstream_instance_ids(session, graph_runner_id, request.target_instance_id)
    if not upstream_instance_ids:
        LOGGER.debug("No upstream instances for target_instance_id=%s", request.target_instance_id)
        return FieldExpressionAutocompleteResponse(suggestions=[])

    eligible_instances = [instance for instance in instances if instance.id in upstream_instance_ids]
    if not eligible_instances:
        LOGGER.debug("No eligible instances after filtering")
        return FieldExpressionAutocompleteResponse(suggestions=[])

    suggestions: list[FieldExpressionSuggestion]

    if phase == SuggestionKind.MODULE:
        suggestions = _build_instance_suggestions(eligible_instances, query)
    elif phase == SuggestionKind.PROPERTY:
        instance_prefix, port_prefix = _parse_query_parts(query)
        suggestions = _build_port_suggestions_with_start_fields(
            session, graph_runner_id, eligible_instances, instance_prefix, port_prefix
        )
    else:
        suggestions = []

    LOGGER.debug(
        "Field expression autocomplete: phase=%s count=%d",
        phase,
        len(suggestions),
    )
    return FieldExpressionAutocompleteResponse(suggestions=suggestions)


def _get_phase_from_query(query: str) -> SuggestionKind:
    """Determine the autocomplete phase based on the query string.

    If the query contains a '.', we're in the port (property) phase.
    Otherwise, we're in the instance (module) phase.
    """
    if "." in query:
        return SuggestionKind.PROPERTY
    return SuggestionKind.MODULE


def _parse_query_parts(query: str) -> tuple[str, str]:
    """Parse the query into instance prefix and port prefix.

    For query "uuid.port", returns ("uuid", "port").
    For query "uuid.", returns ("uuid", "").
    """
    if "." not in query:
        return query, ""
    dot_idx = query.find(".")
    return query[:dot_idx], query[dot_idx + 1 :]


def _build_instance_suggestions(
    instances: Iterable[db.ComponentInstance],
    query: str,
) -> list[FieldExpressionSuggestion]:
    suggestions: list[FieldExpressionSuggestion] = []
    search_term = query.lower() if query else ""

    for instance in instances:
        instance_id_str = str(instance.id)
        instance_name = instance.name or ""
        if search_term and not (search_term in instance_id_str.lower() or search_term in instance_name.lower()):
            continue
        suggestions.append(
            FieldExpressionSuggestion(
                id=instance_id_str,
                label=instance.name or instance_id_str,
                insert_text=f"{instance_id_str}.",
                kind=SuggestionKind.MODULE,
            )
        )

    def sort_key(s: FieldExpressionSuggestion) -> tuple[int, str, str]:
        priority = 0 if s.label.lower().startswith(search_term) else 1
        return (priority, s.label, s.id)

    suggestions.sort(key=sort_key)
    return suggestions


def _build_port_suggestions_with_start_fields(
    session: Session,
    graph_runner_id: UUID,
    instances: Iterable[db.ComponentInstance],
    instance_prefix: str,
    port_prefix: str,
) -> list[FieldExpressionSuggestion]:
    """Build port suggestions, including start node input fields if the instance is a start node."""
    typed_instance = instance_prefix.strip()
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

    search_term = port_prefix.lower() if port_prefix else ""
    suggestions: list[FieldExpressionSuggestion] = []

    is_start = is_start_node(session, graph_runner_id, instance_uuid)

    if is_start:
        component_instance_schema = get_component_instance(session, instance_uuid, is_start_node=True)
        playground_schema = extract_playground_schema_from_component(component_instance_schema)

        if playground_schema:
            for field_name in playground_schema.keys():
                if field_name == "messages":
                    continue

                if search_term and search_term not in field_name.lower():
                    continue

                suggestions.append(
                    FieldExpressionSuggestion(
                        id=f"{instance_uuid}.{field_name}",
                        label=field_name,
                        insert_text=f"{field_name}}}}}",
                        kind=SuggestionKind.PROPERTY,
                    )
                )

    ports = get_output_ports_for_component_version(session, instance.component_version_id)
    for port in ports:
        port_name = port.name or ""
        if not port_name:
            continue
        if search_term and search_term not in port_name.lower():
            continue
        suggestions.append(
            FieldExpressionSuggestion(
                id=f"{instance_uuid}.{port_name}",
                label=port_name,
                insert_text=f"{port_name}}}}}",
                kind=SuggestionKind.PROPERTY,
            )
        )

    def sort_key(s: FieldExpressionSuggestion) -> tuple[int, str]:
        priority = 0 if s.label.lower().startswith(search_term) else 1
        return (priority, s.label)

    suggestions.sort(key=sort_key)
    return suggestions


def _get_upstream_instance_ids(session: Session, graph_runner_id: UUID, target_instance_id: UUID) -> set[UUID]:
    """Return all component instance ids that have a path to the target instance."""
    edges = get_edges(session, graph_runner_id)
    predecessors: dict[UUID, set[UUID]] = defaultdict(set)
    for edge in edges:
        if edge.source_node_id and edge.target_node_id:
            predecessors[edge.target_node_id].add(edge.source_node_id)

    visited_upstream_ids: set[UUID] = set()
    queue: deque[UUID] = deque(predecessors.get(target_instance_id, []))

    while queue:
        node_id = queue.popleft()
        if node_id in visited_upstream_ids:
            continue
        visited_upstream_ids.add(node_id)
        for parent in predecessors.get(node_id, []):
            queue.append(parent)

    return visited_upstream_ids
