import logging
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
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

    context = get_cursor_context(request.expression_text or "", request.cursor_offset)
    if not context:
        return FieldExpressionAutocompleteResponse(suggestions=[])

    instances = list(_list_component_instances(session, graph_runner_id))
    if not instances:
        return FieldExpressionAutocompleteResponse(suggestions=[])

    suggestions: list[FieldExpressionSuggestion]

    if context.phase == "instance":
        suggestions = _build_instance_suggestions(instances, context.instance_token)
    elif context.phase == "port":
        suggestions = _build_port_suggestions(session, instances, context)
    else:
        # TODO: Offer structured key suggestions once metadata is available.
        suggestions = []

    # TODO: Restrict suggestions to upstream instances once graph ordering is exposed.
    LOGGER.debug(
        "Field expression autocomplete: trigger=%s phase=%s count=%d",
        request.trigger.value,
        context.phase,
        len(suggestions),
    )
    return FieldExpressionAutocompleteResponse(suggestions=suggestions)


def _list_component_instances(session: Session, graph_runner_id: UUID) -> Iterable[db.ComponentInstance]:
    return (
        session.query(db.ComponentInstance)
        .join(db.GraphRunnerNode, db.GraphRunnerNode.node_id == db.ComponentInstance.id)
        .filter(db.GraphRunnerNode.graph_runner_id == graph_runner_id)
        .all()
    )


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
    context: FieldExpressionCursorContext,
) -> list[FieldExpressionSuggestion]:
    typed_instance = (context.instance_token or "").strip()
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
    ports = (
        session.query(db.PortDefinition)
        .filter(
            db.PortDefinition.component_version_id == instance.component_version_id,
            db.PortDefinition.port_type == db.PortType.OUTPUT,
        )
        .order_by(db.PortDefinition.name)
        .all()
    )

    prefix = (context.port_token or "").lower()
    suggestions: list[FieldExpressionSuggestion] = []
    for port in ports:
        port_name = port.name or ""
        if prefix and not port_name.lower().startswith(prefix):
            continue
        insert_text = _missing_suffix(port_name, context.port_token or "")
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
