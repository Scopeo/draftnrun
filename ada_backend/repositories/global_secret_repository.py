from typing import Optional
import logging

from sqlalchemy.orm import Session

from ada_backend.database import models as db


LOGGER = logging.getLogger(__name__)


def list_global_secrets(session: Session) -> list[db.GlobalSecret]:
    return session.query(db.GlobalSecret).order_by(db.GlobalSecret.key.asc()).all()


def get_global_secret(session: Session, key: str) -> Optional[db.GlobalSecret]:
    return session.query(db.GlobalSecret).filter(db.GlobalSecret.key == key).first()


def upsert_global_secret(session: Session, key: str, secret: str) -> db.GlobalSecret:
    item = session.query(db.GlobalSecret).filter(db.GlobalSecret.key == key).first()
    if not item:
        LOGGER.info("Creating new global secret with key %s", key)
        item = db.GlobalSecret(key=key)
    else:
        LOGGER.info("Updating existing global secret with key %s", key)
    item.set_secret(secret)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def delete_global_secret(session: Session, key: str) -> None:
    item = session.query(db.GlobalSecret).filter(db.GlobalSecret.key == key).first()
    if not item:
        raise ValueError(f"Global secret with key {key} not found")
    LOGGER.info("Deleting global secret with key %s", key)
    session.delete(item)
    session.commit()
