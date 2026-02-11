"""Database session and engine."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.config import settings
from api.db.models import Base

# Use sync URL for create_async_engine (postgresql+asyncpg://)
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db():
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
