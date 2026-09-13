from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings


settings = get_settings()


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


engine = create_async_engine(normalize_database_url(settings.database_url), future=True, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as db:
        yield db
