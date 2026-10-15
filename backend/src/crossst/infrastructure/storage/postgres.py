from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crossst.core.config import get_settings

# 负责 PostgreSQL 连接管理

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.postgres_dsn,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def check_postgres() -> bool:
    async with engine.connect() as conn:
        result = await conn.execute(text("select 1"))
        return result.scalar_one() == 1


async def close_postgres() -> None:
    await engine.dispose()
