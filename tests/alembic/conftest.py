import pytest

from ada_backend.database import setup_db


@pytest.fixture(autouse=True)
def _bind_sessionlocal_to_alembic_engine(alembic_engine):
    """Ensure internal get_db_session() uses the ephemeral alembic DB for these tests only.

    Rebinds `ada_backend.database.setup_db.SessionLocal` to the provided `alembic_engine`
    for the duration of each alembic test, then restores the original binding.
    """

    original_engine = setup_db.engine
    setup_db.SessionLocal.configure(bind=alembic_engine)
    try:
        yield
    finally:
        setup_db.SessionLocal.configure(bind=original_engine)
