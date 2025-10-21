from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ada_backend.database.models import Base
from settings import settings


def get_db_url() -> str:
    if not settings.ADA_DB_URL:
        raise ValueError("Database URL is not configured. Check your settings.")
    return settings.ADA_DB_URL


engine = create_engine(get_db_url(), echo=False)


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
