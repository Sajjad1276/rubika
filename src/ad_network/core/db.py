from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings


settings = get_settings()
engine = create_async_engine(settings.database_url, future=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as db:
        yield db
