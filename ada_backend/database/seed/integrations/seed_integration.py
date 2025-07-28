from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import upsert_integrations


INTEGRATION_UUIDS = {
    "gmail_sender": UUID("91bb788b-45de-4bbf-86d4-3149fc804b30"),
    "linkup_service": UUID("a1b2c3d4-e5f6-7890-1234-56789abcdef0"),
}


def seed_integrations(session: Session):
    gmail_sender_integration = db.Integration(
        id=INTEGRATION_UUIDS["gmail_sender"],
        name="google",
        service="gmail sender",
    )
    linkup_service_integration = db.Integration(
        id=INTEGRATION_UUIDS["linkup_service"],
        name="linkup",
        service="linkup service",
    )
    upsert_integrations(session, [gmail_sender_integration, linkup_service_integration])
