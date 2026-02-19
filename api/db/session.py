"""Database session and engine."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine.url import URL

from api.config import settings
from api.db.models import Base

DATABASE_URL = URL.create(
    drivername="postgresql+asyncpg",
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
)

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.log_level.upper() == "DEBUG",
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db():
    """Create tables if they don't exist (safe to call on every startup)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)