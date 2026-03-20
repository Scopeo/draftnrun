import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from ada_backend.database import trace_models  # noqa: F401  # Import to register trace models with Base.metadata
from ada_backend.database.models import Base
from settings import settings

LOGGER = logging.getLogger(__name__)


def get_db_url() -> str:
    if not settings.ADA_DB_URL:
        raise ValueError("Database URL is not configured. Check your settings.")
    return settings.ADA_DB_URL


def _build_engine():
    url = get_db_url()
    kwargs = {"echo": False}
    if not url.startswith("sqlite"):
        kwargs.update(
            pool_size=settings.ADA_DB_POOL_SIZE,
            max_overflow=settings.ADA_DB_MAX_OVERFLOW,
            pool_timeout=settings.ADA_DB_POOL_TIMEOUT,
            pool_recycle=settings.ADA_DB_POOL_RECYCLE,
            pool_pre_ping=True,
        )
    return create_engine(url, **kwargs)


engine = _build_engine()


# Enable SQLite foreign key support
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


if hasattr(engine.pool, "size"):

    @event.listens_for(engine, "checkout")
    def _on_checkout(dbapi_conn, connection_rec, connection_proxy):
        pool = engine.pool
        LOGGER.debug(
            "Pool checkout: checked_out=%s checked_in=%s overflow=%s pool_size=%s",
            pool.checkedout(),
            pool.checkedin(),
            pool.overflow(),
            pool.size(),
        )

    @event.listens_for(engine, "checkin")
    def _on_checkin(dbapi_conn, connection_rec):
        pool = engine.pool
        LOGGER.debug(
            "Pool checkin: checked_out=%s checked_in=%s overflow=%s pool_size=%s",
            pool.checkedout(),
            pool.checkedin(),
            pool.overflow(),
            pool.size(),
        )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize the database by creating tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Provide a scoped session for FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """Context manager for database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
