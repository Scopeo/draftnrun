from typing import Optional
from uuid import UUID
import logging
import secrets

from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def generate_widget_key() -> str:
    return secrets.token_urlsafe(32)


def get_widget_by_id(session: Session, widget_id: UUID) -> Optional[db.Widget]:
    return session.query(db.Widget).filter(db.Widget.id == widget_id).first()


def get_widget_by_key(session: Session, widget_key: str) -> Optional[db.Widget]:
    return session.query(db.Widget).filter(db.Widget.widget_key == widget_key).first()


def get_widgets_by_organization(session: Session, organization_id: UUID) -> list[db.Widget]:
    return (
        session.query(db.Widget)
        .filter(db.Widget.organization_id == organization_id)
        .order_by(db.Widget.created_at.desc())
        .all()
    )


def get_widgets_by_project(session: Session, project_id: UUID) -> list[db.Widget]:
    return (
        session.query(db.Widget).filter(db.Widget.project_id == project_id).order_by(db.Widget.created_at.desc()).all()
    )


def create_widget(
    session: Session,
    project_id: UUID,
    organization_id: UUID,
    name: str,
    config: Optional[dict] = None,
) -> db.Widget:
    widget = db.Widget(
        widget_key=generate_widget_key(),
        project_id=project_id,
        organization_id=organization_id,
        name=name,
        is_enabled=True,
        config=config or {},
    )
    session.add(widget)
    session.commit()
    session.refresh(widget)
    return widget


def update_widget(
    session: Session,
    widget_id: UUID,
    name: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    config: Optional[dict] = None,
) -> Optional[db.Widget]:
    widget = get_widget_by_id(session, widget_id)
    if not widget:
        return None

    if name is not None:
        widget.name = name
    if is_enabled is not None:
        widget.is_enabled = is_enabled
    if config is not None:
        widget.config = config

    session.commit()
    session.refresh(widget)
    return widget


def regenerate_widget_key(session: Session, widget_id: UUID) -> Optional[db.Widget]:
    widget = get_widget_by_id(session, widget_id)
    if not widget:
        return None

    widget.widget_key = generate_widget_key()
    session.commit()
    session.refresh(widget)
    return widget


def delete_widget(session: Session, widget_id: UUID) -> bool:
    widget = get_widget_by_id(session, widget_id)
    if not widget:
        return False

    session.delete(widget)
    session.commit()
    return True
