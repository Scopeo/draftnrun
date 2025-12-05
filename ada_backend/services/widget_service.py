from typing import Optional
from uuid import UUID, uuid4
import logging

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import EnvType, CallType
from ada_backend.repositories.widget_repository import (
    get_widget_by_id,
    get_widget_by_key,
    get_widgets_by_organization,
    get_widgets_by_project,
    create_widget as repo_create_widget,
    update_widget as repo_update_widget,
    regenerate_widget_key as repo_regenerate_widget_key,
    delete_widget as repo_delete_widget,
)
from ada_backend.repositories.project_repository import get_project
from ada_backend.schemas.widget_schema import (
    WidgetSchema,
    WidgetPublicConfigSchema,
    WidgetConfig,
    WidgetTheme,
    WidgetCreateSchema,
    WidgetUpdateSchema,
    WidgetChatResponse,
)
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.services.errors import ProjectNotFound

LOGGER = logging.getLogger(__name__)


class WidgetNotFound(Exception):
    """Raised when a widget is not found."""

    def __init__(self, widget_id: Optional[UUID] = None, widget_key: Optional[str] = None):
        if widget_id:
            super().__init__(f"Widget with id {widget_id} not found")
        elif widget_key:
            super().__init__(f"Widget with key {widget_key} not found")
        else:
            super().__init__("Widget not found")


class WidgetDisabled(Exception):
    """Raised when trying to use a disabled widget."""

    def __init__(self, widget_key: str):
        super().__init__(f"Widget {widget_key} is disabled")


def _widget_to_schema(widget: db.Widget) -> WidgetSchema:
    """Convert a Widget model to a WidgetSchema."""
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
    """Convert a Widget model to a public config schema (for iframe)."""
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


# --- Public endpoints (for widget iframe) ---
def get_widget_public_config_service(session: Session, widget_key: str) -> WidgetPublicConfigSchema:
    """Get public widget configuration by widget_key (for iframe)."""
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
    """
    Handle chat message for a widget.
    Runs the associated project's workflow with the message.
    """
    widget = get_widget_by_key(session, widget_key)
    if not widget:
        raise WidgetNotFound(widget_key=widget_key)
    if not widget.is_enabled:
        raise WidgetDisabled(widget_key)

    # Build input data for the agent
    messages = history.copy() if history else []
    messages.append({"role": "user", "content": message})

    input_data = {
        "messages": messages,
    }
    if conversation_id:
        input_data["conversation_id"] = conversation_id

    # Run the project's production environment
    result = await run_env_agent(
        session=session,
        project_id=widget.project_id,
        env=EnvType.PRODUCTION,
        input_data=input_data,
        call_type=CallType.API,
    )

    # Generate a new conversation_id if none was provided (first message)
    if not conversation_id:
        conversation_id = str(uuid4())

    return WidgetChatResponse(
        response=result.message,
        conversation_id=conversation_id,
        trace_id=result.trace_id,
        artifacts=result.artifacts,
        error=result.error,
    )


# --- Admin endpoints (for dashboard) ---
def list_widgets_service(session: Session, organization_id: UUID) -> list[WidgetSchema]:
    """List all widgets for an organization."""
    widgets = get_widgets_by_organization(session, organization_id)
    return [_widget_to_schema(w) for w in widgets]


def get_widget_service(session: Session, widget_id: UUID) -> WidgetSchema:
    """Get a widget by ID."""
    widget = get_widget_by_id(session, widget_id)
    if not widget:
        raise WidgetNotFound(widget_id=widget_id)
    return _widget_to_schema(widget)


def get_widget_by_project_service(session: Session, project_id: UUID) -> Optional[WidgetSchema]:
    """Get the widget for a specific project (if exists)."""
    widgets = get_widgets_by_project(session, project_id)
    if not widgets:
        return None
    # Return the first widget (typically there's only one per project)
    return _widget_to_schema(widgets[0])


def create_widget_service(
    session: Session,
    organization_id: UUID,
    data: WidgetCreateSchema,
) -> WidgetSchema:
    """Create a new widget for a project."""
    # Verify project exists and belongs to organization
    project = get_project(session, project_id=data.project_id)
    if not project:
        raise ProjectNotFound(data.project_id)
    if project.organization_id != organization_id:
        raise ProjectNotFound(data.project_id)

    # Convert WidgetConfig to dict for storage
    config_dict = {}
    if data.config:
        config_dict = {
            "theme": data.config.theme.model_dump() if data.config.theme else {},
            "header_message": data.config.header_message,
            "first_messages": data.config.first_messages,
            "suggestions": data.config.suggestions,
            "placeholder_text": data.config.placeholder_text,
            "powered_by_visible": data.config.powered_by_visible,
            "rate_limit_config": data.config.rate_limit_config,
            "rate_limit_chat": data.config.rate_limit_chat,
            "allowed_origins": data.config.allowed_origins,
        }

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
    """Update a widget."""
    widget = get_widget_by_id(session, widget_id)
    if not widget:
        raise WidgetNotFound(widget_id=widget_id)

    # Convert WidgetConfig to dict if provided
    config_dict = None
    if data.config:
        config_dict = {
            "theme": data.config.theme.model_dump() if data.config.theme else {},
            "header_message": data.config.header_message,
            "first_messages": data.config.first_messages,
            "suggestions": data.config.suggestions,
            "placeholder_text": data.config.placeholder_text,
            "powered_by_visible": data.config.powered_by_visible,
            "rate_limit_config": data.config.rate_limit_config,
            "rate_limit_chat": data.config.rate_limit_chat,
            "allowed_origins": data.config.allowed_origins,
        }

    updated = repo_update_widget(
        session=session,
        widget_id=widget_id,
        name=data.name,
        is_enabled=data.is_enabled,
        config=config_dict,
    )
    return _widget_to_schema(updated)


def regenerate_widget_key_service(session: Session, widget_id: UUID) -> WidgetSchema:
    """Regenerate a widget's public key."""
    widget = repo_regenerate_widget_key(session, widget_id)
    if not widget:
        raise WidgetNotFound(widget_id=widget_id)
    return _widget_to_schema(widget)


def delete_widget_service(session: Session, widget_id: UUID) -> bool:
    """Delete a widget."""
    success = repo_delete_widget(session, widget_id)
    if not success:
        raise WidgetNotFound(widget_id=widget_id)
    return True
