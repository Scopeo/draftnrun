from contextlib import asynccontextmanager
import asyncio

from typing import AsyncGenerator
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine
from sqlalchemy import event, create_engine
from ada_backend.database.models import Base
from settings import settings


def get_sync_db_url() -> str:
    if not settings.ADA_SYNC_DB_URL:
        raise ValueError("Database URL with sync syntax is not configured.")
    return settings.ADA_SYNC_DB_URL


def get_db_url() -> str:
    if not settings.ADA_DB_URL:
        raise ValueError("Database URL is not configured.")
    return settings.ADA_DB_URL


engine: AsyncEngine = create_async_engine(get_db_url(), echo=False)
sync_engine = create_engine(get_sync_db_url(), echo=False)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


def get_sync_db():
    """Provide a scoped session for FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(init_db())
