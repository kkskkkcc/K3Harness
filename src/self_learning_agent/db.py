from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from self_learning_agent.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
if settings.database_url.startswith("sqlite"):
    from pathlib import Path

    Path("data").mkdir(parents=True, exist_ok=True)
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.app_env == "development",
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def init_db() -> None:
    """Create the portable local schema without requiring Docker or Alembic."""
    from self_learning_agent import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
