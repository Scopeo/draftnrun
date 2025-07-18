from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from settings import settings


def get_session_evaluations():
    """Get a database session for the evaluations database."""
    if not settings.EVALUATIONS_DB_URL:
        raise ValueError("EVALUATIONS_DB_URL is not set")
    engine = create_engine(settings.EVALUATIONS_DB_URL, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    return session
