import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def get_webhook_by_external_client_id(
    session: Session, provider: db.WebhookProvider, external_client_id: str
) -> Optional[db.Webhook]:
    return (
        session.query(db.Webhook)
        .filter(db.Webhook.provider == provider, db.Webhook.external_client_id == external_client_id)
        .first()
    )


def get_enabled_webhook_triggers(session: Session, webhook_id: UUID) -> List[db.IntegrationTrigger]:
    return (
        session.query(db.IntegrationTrigger)
        .filter(
            db.IntegrationTrigger.webhook_id == webhook_id,
            db.IntegrationTrigger.enabled.is_(True),
        )
        .all()
    )
