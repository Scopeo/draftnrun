import logging
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import CallType, EnvType
from ada_backend.repositories.project_repository import get_project
from ada_backend.repositories.widget_repository import (
    create_widget as repo_create_widget,
)
from ada_backend.repositories.widget_repository import (
    delete_widget as repo_delete_widget,
)
from ada_backend.repositories.widget_repository import (
    get_widget_by_id,
    get_widget_by_key,
    get_widgets_by_organization,
    get_widgets_by_project,
)
from ada_backend.repositories.widget_repository import (
    regenerate_widget_key as repo_regenerate_widget_key,
)
from ada_backend.repositories.widget_repository import (
    update_widget as repo_update_widget,
)
from ada_backend.schemas.widget_schema import (
    WidgetChatResponse,
    WidgetConfig,
    WidgetCreateSchema,
    WidgetPublicConfigSchema,
    WidgetSchema,
    WidgetTheme,
    WidgetUpdateSchema,
)
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.services.errors import ProjectNotFound, WidgetDisabled, WidgetNotFound

LOGGER = logging.getLogger(__name__)


def _widget_to_schema(widget: db.Widget) -> WidgetSchema:
    config_dict = widget.config or {}
    theme_dict = config_dict.get("theme", {})

    return WidgetSchema(
        id=widget.id,
        widget_key=widget.widget_key,
        project_id=widget.project_id,
        organization_id=widget.organization_id,
        name=widget.name,
        is_enabled=widget.is_enabled,
        config=WidgetConfig(
            theme=WidgetTheme(**theme_dict) if theme_dict else WidgetTheme(),
            header_message=config_dict.get("header_message"),
            first_messages=config_dict.get("first_messages", []),
            suggestions=config_dict.get("suggestions", []),
            placeholder_text=config_dict.get("placeholder_text", "Type a message..."),
            powered_by_visible=config_dict.get("powered_by_visible", True),
            rate_limit_config=config_dict.get("rate_limit_config", 10),
            rate_limit_chat=config_dict.get("rate_limit_chat", 5),
            allowed_origins=config_dict.get("allowed_origins", []),
        ),
        created_at=str(widget.created_at) if widget.created_at else None,
        updated_at=str(widget.updated_at) if widget.updated_at else None,
    )


def _widget_to_public_config(widget: db.Widget) -> WidgetPublicConfigSchema:
    config_dict = widget.config or {}
    theme_dict = config_dict.get("theme", {})

    return WidgetPublicConfigSchema(
        widget_key=widget.widget_key,
        name=widget.name,
        theme=WidgetTheme(**theme_dict) if theme_dict else WidgetTheme(),
        header_message=config_dict.get("header_message"),
        first_messages=config_dict.get("first_messages", []),
        suggestions=config_dict.get("suggestions", []),
        placeholder_text=config_dict.get("placeholder_text", "Type a message..."),
        powered_by_visible=config_dict.get("powered_by_visible", True),
    )


def get_widget_public_config_service(session: Session, widget_key: str) -> WidgetPublicConfigSchema:
    widget = get_widget_by_key(session, widget_key)
    if not widget:
        raise WidgetNotFound(widget_key=widget_key)
    if not widget.is_enabled:
        raise WidgetDisabled(widget_key)
    return _widget_to_public_config(widget)


async def widget_chat_service(
    session: Session,
    widget_key: str,
    message: str,
    history: list[dict],
    conversation_id: Optional[str] = None,
) -> WidgetChatResponse:
    widget = get_widget_by_key(session, widget_key)
    if not widget:
        raise WidgetNotFound(widget_key=widget_key)
    if not widget.is_enabled:
        raise WidgetDisabled(widget_key)

    messages = history.copy() if history else []
    messages.append({"role": "user", "content": message})

    input_data = {
        "messages": messages,
    }
    if conversation_id:
        input_data["conversation_id"] = conversation_id

    result = await run_env_agent(
        session=session,
        project_id=widget.project_id,
        env=EnvType.PRODUCTION,
        input_data=input_data,
        call_type=CallType.API,
    )

    if not conversation_id:
        conversation_id = str(uuid4())

    return WidgetChatResponse(
        response=result.message,
        conversation_id=conversation_id,
        trace_id=result.trace_id,
        artifacts=result.artifacts,
        error=result.error,
    )


def list_widgets_service(session: Session, organization_id: UUID) -> list[WidgetSchema]:
    widgets = get_widgets_by_organization(session, organization_id)
    return [_widget_to_schema(w) for w in widgets]


def get_widget_service(session: Session, widget_id: UUID) -> WidgetSchema:
    widget = get_widget_by_id(session, widget_id)
    if not widget:
        raise WidgetNotFound(widget_id=widget_id)
    return _widget_to_schema(widget)


def get_widget_by_project_service(session: Session, project_id: UUID) -> Optional[WidgetSchema]:
    widgets = get_widgets_by_project(session, project_id)
    if not widgets:
        return None
    return _widget_to_schema(widgets[0])


def create_widget_service(
    session: Session,
    organization_id: UUID,
    data: WidgetCreateSchema,
) -> WidgetSchema:
    project = get_project(session, project_id=data.project_id)
    if not project:
        raise ProjectNotFound(data.project_id)
    if project.organization_id != organization_id:
        raise ProjectNotFound(data.project_id)

    config_dict = data.config.model_dump() if data.config else {}

    widget = repo_create_widget(
        session=session,
        project_id=data.project_id,
        organization_id=organization_id,
        name=data.name,
        config=config_dict,
    )
    return _widget_to_schema(widget)


def update_widget_service(
    session: Session,
    widget_id: UUID,
    data: WidgetUpdateSchema,
) -> WidgetSchema:
    widget = get_widget_by_id(session, widget_id)
    if not widget:
        raise WidgetNotFound(widget_id=widget_id)

    config_dict = data.config.model_dump() if data.config else None

    updated = repo_update_widget(
        session=session,
        widget_id=widget_id,
        name=data.name,
        is_enabled=data.is_enabled,
        config=config_dict,
    )
    return _widget_to_schema(updated)


def regenerate_widget_key_service(session: Session, widget_id: UUID) -> WidgetSchema:
    widget = repo_regenerate_widget_key(session, widget_id)
    if not widget:
        raise WidgetNotFound(widget_id=widget_id)
    return _widget_to_schema(widget)


def delete_widget_service(session: Session, widget_id: UUID) -> bool:
    success = repo_delete_widget(session, widget_id)
    if not success:
        raise WidgetNotFound(widget_id=widget_id)
    return True
